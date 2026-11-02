"""Camera department backends."""
from __future__ import annotations

import copy
import json
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

from ..ffmpeg import ffpath, font_file, run
from ..prompt_compiler import GenerationRequest

VIDEO_ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]


class VideoBackend:
    name = "base"

    def generate(self, req: GenerationRequest, out_path: Path, previz: Optional[dict] = None) -> Path:
        raise NotImplementedError


class PrevizVideo(VideoBackend):
    """Animatic renderer: real moving clips with staging, camera moves, framing and
    dialogue, generated with ffmpeg only. Lets you edit and time the whole film
    before (or without) spending GPU time on final pixels."""

    name = "previz (built-in animatic)"

    def generate(self, req: GenerationRequest, out_path: Path, previz: Optional[dict] = None) -> Path:
        previz = previz or {}
        W, H, fps, D = req.width, req.height, req.fps, max(0.5, req.duration)
        frames = max(1, int(round(D * fps)))
        pal = [c.lstrip("#") for c in (req.palette or ["101827", "1e3a8a"])]
        c0, c1 = pal[0], pal[1 % len(pal)]
        tmp = Path(tempfile.mkdtemp(prefix="previz_"))
        font = font_file()
        fontarg = f"fontfile='{ffpath(font)}':" if font else ""

        def text(t: str, x: str, y: str, size: int, color: str = "white", box: bool = True) -> str:
            f = tmp / f"t_{uuid.uuid4().hex[:6]}.txt"
            f.write_text(t)
            b = ":box=1:boxcolor=black@0.45:boxborderw=8" if box else ""
            return (f"drawtext={fontarg}textfile='{ffpath(f)}':expansion=none:fontsize={size}:"
                    f"fontcolor={color}:x={x}:y={y}{b}")

        size = req.camera.get("size", "")
        filters: list[str] = []
        # --- staging: characters as coloured stand-ins blocked on their side of the 180 line
        figures = previz.get("figures", [])
        close = any(k in size for k in ("close-up", "over-the-shoulder"))
        ots = "over-the-shoulder" in size
        for i, fig in enumerate(figures):
            n = len(figures)
            fw = int(W * (0.26 if close and n == 1 else 0.16 if close else 0.1))
            fh = int(H * (0.62 if close else 0.5))
            side = fig.get("side", "neutral")
            if ots:   # speaker mid-ground facing camera, listener's shoulder in the foreground
                cx = 0.42 if side != "right_to_left" else 0.58
                if i == 1:
                    fw, fh = int(W * 0.24), int(H * 0.55)
                    cx = 0.84 if side != "right_to_left" else 0.16
            elif n == 1:
                cx = {"left_to_right": 0.38, "right_to_left": 0.62}.get(side, 0.5)
            else:
                cx = 0.3 + 0.4 * i / max(1, n - 1)
            head = min(fw // 2, int(H * 0.2))
            x, y = int(W * cx - fw / 2), int(H - fh)
            col = fig.get("color", "#8b5cf6").lstrip("#")
            alpha = 0.55 if ots and i == 1 else 0.9
            filters.append(f"drawbox=x={x}:y={y}:w={fw}:h={fh}:color=0x{col}@{alpha}:t=fill")
            filters.append(f"drawbox=x={x + (fw - head) // 2}:y={y - head - 6}:w={head}:h={head}:color=0x{col}@{alpha}:t=fill")
            filters.append(text(fig.get("name", "?"), str(x + (fw - head) // 2), str(max(40, y - head - 40)),
                                max(14, H // 28)))
        if previz.get("insert"):
            bw, bh = int(W * 0.3), int(H * 0.35)
            filters.append(f"drawbox=x={(W - bw) // 2}:y={(H - bh) // 2}:w={bw}:h={bh}:color=0x{pal[2 % len(pal)]}@0.9:t=fill")
            filters.append(text(previz["insert"], "(w-text_w)/2", "(h-text_h)/2", max(16, H // 22), box=False))
        if "extreme wide" in size or not figures and not previz.get("insert"):
            filters.append(f"drawbox=x=0:y={int(H * 0.7)}:w={W}:h={int(H * 0.3)}:color=0x{pal[-1]}@0.25:t=fill")
        # --- camera movement
        mv = req.camera.get("movement", "static")
        pad_scale = "scale=iw*1.2:ih*1.2"
        if mv in ("pan left", "truck left"):
            filters += [pad_scale, f"crop={W}:{H}:x='(in_w-out_w)*(1-t/{D})':y='(in_h-out_h)/2'"]
        elif mv in ("pan right", "truck right"):
            filters += [pad_scale, f"crop={W}:{H}:x='(in_w-out_w)*t/{D}':y='(in_h-out_h)/2'"]
        elif mv in ("tilt up", "crane up"):
            filters += [pad_scale, f"crop={W}:{H}:x='(in_w-out_w)/2':y='(in_h-out_h)*(1-t/{D})'"]
        elif mv in ("tilt down", "crane down"):
            filters += [pad_scale, f"crop={W}:{H}:x='(in_w-out_w)/2':y='(in_h-out_h)*t/{D}'"]
        elif mv in ("handheld", "steadicam follow", "orbit"):
            amp = 10 if mv == "handheld" else 4
            filters += [pad_scale, f"crop={W}:{H}:x='(in_w-out_w)/2+{amp}*sin(t*3.1)+{amp/2}*sin(t*7.3)'"
                                   f":y='(in_h-out_h)/2+{amp*0.7}*sin(t*2.3)'"]
        elif mv in ("dolly in", "slow zoom in", "dolly out", "slow zoom out"):
            z = f"1+0.18*on/{frames}" if "in" in mv.split()[-1] else f"1.18-0.18*on/{frames}"
            filters.append(f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}")
        filters.append(f"scale={W}:{H},setsar=1")
        # --- HUD + subtitles
        if previz.get("label"):
            filters.append(text(previz["label"], "16", "14", max(12, H // 36)))
        if previz.get("subtitle"):
            filters.append(text(previz["subtitle"], "(w-text_w)/2", f"h-text_h-{max(16, H // 18)}", max(14, H // 26),
                                color="yellow"))
        src = f"gradients=s={W}x{H}:c0=0x{c0}:c1=0x{c1}:speed=0.008:duration={D}:rate={fps}:seed={req.seed % 2**31}"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        script = tmp / "filter.txt"
        script.write_text(",".join(filters))
        run(["-f", "lavfi", "-i", src, "-filter_script:v", script, "-t", f"{D:.3f}", "-r", fps,
             "-frames:v", frames, *VIDEO_ENC, "-an", out_path])
        return out_path


class ComfyUIVideo(VideoBackend):
    """Runs any open-weight video model you host in ComfyUI (Wan 2.x, HunyuanVideo,
    LTX-Video, CogVideoX, ...). Export your workflow with "Save (API Format)" and put
    tokens such as {{prompt}}, {{negative_prompt}}, {{seed}}, {{width}}, {{height}},
    {{frames}}, {{fps}}, {{ref_image}} where the values go."""

    name = "comfyui"

    def __init__(self, url: str, workflow_path: str, timeout: float = 3600):
        self.url = url.rstrip("/")
        self.workflow_path = Path(workflow_path)
        if not self.workflow_path.is_absolute():
            self.workflow_path = Path(__file__).resolve().parents[2] / workflow_path
        self.timeout = timeout
        self.name = f"comfyui @ {self.url}"

    def _upload(self, path: str) -> str:
        with open(path, "rb") as f:
            r = httpx.post(f"{self.url}/upload/image", files={"image": (Path(path).name, f)}, data={"overwrite": "true"},
                           timeout=120)
        r.raise_for_status()
        return r.json()["name"]

    @staticmethod
    def fill(node: Any, values: dict[str, Any]) -> Any:
        if isinstance(node, dict):
            return {k: ComfyUIVideo.fill(v, values) for k, v in node.items()}
        if isinstance(node, list):
            return [ComfyUIVideo.fill(v, values) for v in node]
        if isinstance(node, str):
            for k, v in values.items():
                tok = "{{" + k + "}}"
                if node == tok:
                    return v  # keep native type (int seed, etc.)
                if tok in node:
                    node = node.replace(tok, str(v))
        return node

    def generate(self, req: GenerationRequest, out_path: Path, previz: Optional[dict] = None) -> Path:
        wf = json.loads(self.workflow_path.read_text())
        values: dict[str, Any] = {
            "prompt": req.prompt, "negative_prompt": req.negative_prompt, "seed": req.seed,
            "width": req.width - req.width % 16, "height": req.height - req.height % 16, "fps": req.fps,
            "frames": int(round(req.duration * req.fps)) // 4 * 4 + 1,  # 4k+1 frames, common for video DiTs
            "lora": req.loras[0] if req.loras else "",
        }
        if req.reference_images:
            values["ref_image"] = self._upload(req.reference_images[0])
        prompt = self.fill(copy.deepcopy(wf), values)
        r = httpx.post(f"{self.url}/prompt", json={"prompt": prompt, "client_id": "cuestudio"}, timeout=60)
        r.raise_for_status()
        pid = r.json()["prompt_id"]
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            h = httpx.get(f"{self.url}/history/{pid}", timeout=30).json()
            if pid in h:
                entry = h[pid]
                if entry.get("status", {}).get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI error: {entry['status']}")
                for out in entry.get("outputs", {}).values():
                    for key in ("videos", "gifs", "images"):
                        for f in out.get(key, []):
                            if Path(f["filename"]).suffix.lower() in (".mp4", ".webm", ".mov", ".gif", ".webp"):
                                data = httpx.get(f"{self.url}/view", params={"filename": f["filename"],
                                                 "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")},
                                                 timeout=300).content
                                raw = out_path.with_suffix(Path(f["filename"]).suffix + ".src")
                                raw.write_bytes(data)
                                run(["-i", raw, "-vf", f"scale={req.width}:{req.height}:force_original_aspect_ratio=increase,"
                                     f"crop={req.width}:{req.height},fps={req.fps}", *VIDEO_ENC, "-an", out_path])
                                raw.unlink(missing_ok=True)
                                return out_path
                raise RuntimeError("ComfyUI finished without a video output")
            time.sleep(2)
        raise TimeoutError("ComfyUI generation timed out")
