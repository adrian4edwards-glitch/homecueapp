"""Thin ffmpeg helpers."""
from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

SR = 48000  # project audio sample rate


class FFmpegError(RuntimeError):
    pass


def run(args: list[str]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise FFmpegError(f"ffmpeg failed ({p.returncode}): {p.stderr[-2000:]}\ncmd: {' '.join(cmd)[:1500]}")


def probe_duration(path: str | Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    try:
        return float(json.loads(p.stdout)["format"]["duration"])
    except Exception:
        return 0.0


@lru_cache(maxsize=1)
def font_file() -> str:
    for c in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "C:/Windows/Fonts/arial.ttf"]:
        if Path(c).exists():
            return c
    if shutil.which("fc-match"):
        out = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True).stdout
        if out:
            return out
    return ""


def ffpath(p: str | Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def load_audio(path: str | Path, sr: int = SR) -> np.ndarray:
    """Decode any audio file to mono float32 at `sr`."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                       capture_output=True)
    if p.returncode != 0:
        raise FFmpegError(p.stderr.decode()[-1000:])
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def save_audio(samples: np.ndarray, path: str | Path, sr: int = SR) -> None:
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ac", "1", "-ar", str(sr), "-i", "-",
                        "-ac", "2", str(path)], input=samples.astype(np.float32).tobytes(), capture_output=True)
    if p.returncode != 0:
        raise FFmpegError(p.stderr.decode()[-1000:])
