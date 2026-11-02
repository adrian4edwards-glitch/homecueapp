"""Production pipeline: generate every asset, then edit, mix, grade and export.

    shots  --(video backend)-->  clips  ----\
    lines  --(voice backend)-->  dialogue ---+--> timeline --> edit (xfade/cuts)
    scenes --(music backend)-->  score  ----/                  mix (duck, loudness)
    cues   --(sfx backend)---->  sfx   ----/                   grade, subtitles, EDL
"""
from __future__ import annotations

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import backends
from .config import settings
from .ffmpeg import SR, ffpath, load_audio, probe_duration, run
from .backends.video import VIDEO_ENC
from .models import Project, RenderOutput, Scene, Shot, Status, Transition, digest
from .prompt_compiler import compile_shot
from .storage import ProjectStore

log = logging.getLogger(__name__)
Progress = Callable[[float, str], None]

XFADE = {Transition.dissolve: "fade", Transition.fade_black: "fadeblack", Transition.fade_white: "fadewhite",
         Transition.wipe_left: "wipeleft", Transition.wipe_right: "wiperight", Transition.slide_left: "slideleft",
         Transition.circle_open: "circleopen"}
GRADES = {
    "teal_orange": "colorbalance=rs=-0.05:bs=0.08:rh=0.08:bh=-0.06,eq=contrast=1.08:saturation=1.1",
    "warm": "colorbalance=rm=0.06:bm=-0.05,eq=saturation=1.05",
    "cool": "colorbalance=bm=0.07:rm=-0.04,eq=contrast=1.05",
    "noir": "hue=s=0,eq=contrast=1.3",
    "pastel": "eq=saturation=0.8:brightness=0.04:contrast=0.92",
    "vivid": "eq=saturation=1.35:contrast=1.08",
    "none": "null",
}


@dataclass
class Entry:
    scene: Scene
    shot: Shot
    start: float          # global timeline start
    duration: float
    transition: Transition
    tdur: float           # overlap with previous entry


@dataclass
class AudioEvent:
    path: Path
    start: float
    gain: float
    stem: str             # dialogue | music | sfx
    fade: float = 0.0


def build_timeline(scenes: list[Scene]) -> tuple[list[Entry], float]:
    entries: list[Entry] = []
    t = 0.0
    for sc_i, sc in enumerate(scenes):
        for sh_i, sh in enumerate(sc.shots):
            tr = sh.transition_in if entries else Transition.cut
            if tr in XFADE and entries:
                base = 1.0 if tr in (Transition.fade_black, Transition.fade_white) else 0.6
                td = round(min(base, 0.45 * min(entries[-1].duration, sh.duration)), 3)
            else:
                td = 0.0
            start = t - td
            entries.append(Entry(sc, sh, start, sh.duration, tr, td))
            t = start + sh.duration
    return entries, t


def movavg(x: np.ndarray, k: int) -> np.ndarray:
    if k <= 1 or len(x) == 0:
        return x
    c = np.cumsum(np.concatenate([[0.0], x]))
    half = k // 2
    idx = np.arange(len(x))
    lo, hi = np.clip(idx - half, 0, len(x)), np.clip(idx + half + 1, 0, len(x))
    return ((c[hi] - c[lo]) / (hi - lo)).astype(np.float32)


def fmt_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def fmt_tc(t: float, fps: int) -> str:
    f = int(round(t * fps))
    return f"{f // (3600 * fps):02}:{f // (60 * fps) % 60:02}:{f // fps % 60:02}:{f % fps:02}"


class Studio:
    def __init__(self, store: ProjectStore):
        self.store = store

    # ================================================================ generation
    def generate_shot(self, project: Project, scene: Scene, shot: Shot, force: bool = False) -> Shot:
        req = compile_shot(project.bible, scene, shot)
        vb = backends.video_backend()
        key = digest(req.to_dict(), vb.name)
        existing = self.store.abspath(project.id, shot.clip_path)
        if not force and existing and existing.exists() and (shot.gen_key == key or shot.status == Status.approved):
            return shot
        shot.prompt = req.prompt
        shot.status = Status.generating
        names = {c.id: c for c in project.bible.characters}
        previz = {
            "label": f"SC {scene.number} | {shot.number} | {shot.size.value.upper()} | {shot.angle.value} | "
                     f"{shot.movement.value} | {shot.lens_mm}mm",
            "figures": [{"name": names[c].name, "color": names[c].color, "side": shot.screen_direction}
                        for c in shot.character_ids if c in names],
            "subtitle": " / ".join(f"{names[l.character_id].name.upper()}: {l.text}"
                                   for l in shot.dialogue if l.character_id in names)[:140],
            "insert": next((p.name.upper() for p in project.bible.props if p.id in shot.prop_ids), None),
        }
        take = len(shot.takes) + (1 if shot.clip_path else 0) + 1
        out = self.store.media(project.id, "shots") / f"{shot.id}_t{take}.mp4"
        try:
            vb.generate(req, out, previz)
        except Exception as e:
            shot.status, shot.error = Status.failed, str(e)[:500]
            raise
        if shot.clip_path:
            shot.takes.append(shot.clip_path)
        shot.clip_path, shot.gen_key, shot.status, shot.error = self.store.rel(project.id, out), key, Status.ready, ""
        return shot

    def generate_dialogue(self, project: Project, shot: Shot) -> None:
        tts = backends.tts_backend()
        for line in shot.dialogue:
            c = project.bible.character(line.character_id)
            voice = c.voice.model_dump() if c else {}
            key = digest(line.text, voice, line.emotion, tts.name)
            out = self.store.media(project.id, "dialogue") / f"{line.id}_{key}.wav"
            if not out.exists():
                tts.speak(line.text, voice, out, line.emotion)
            line.audio_path, line.duration = self.store.rel(project.id, out), round(probe_duration(out), 3)

    def generate_sfx(self, project: Project, shot: Shot) -> None:
        sb = backends.sfx_backend()
        for cue in shot.sounds:
            key = digest(cue.description, cue.duration, sb.name)
            out = self.store.media(project.id, "sfx") / f"{cue.id}_{key}.wav"
            if not out.exists():
                sb.compose(cue.description, cue.duration, out)
            cue.audio_path = self.store.rel(project.id, out)

    def generate_music(self, project: Project, scene: Scene) -> None:
        if not scene.music_cue:
            return
        mb = backends.music_backend()
        dur = round(scene.duration + 1.0, 1)
        prompt = f"{scene.music_cue}. {project.bible.style.music_style}. Mood: {scene.mood}."
        key = digest(prompt, dur, mb.name)
        out = self.store.media(project.id, "music") / f"{scene.id}_{key}.wav"
        if not out.exists():
            mb.compose(prompt, dur, out)
        scene.music_path = self.store.rel(project.id, out)

    def produce(self, project: Project, scenes: list[Scene], progress: Progress, force: bool = False) -> list[str]:
        """Generate all assets for the given scenes in parallel. Returns errors."""
        jobs: list[tuple[str, Callable[[], None]]] = []
        for sc in scenes:
            jobs.append((f"score {sc.heading}", lambda sc=sc: self.generate_music(project, sc)))
            for sh in sc.shots:
                jobs.append((f"shot {sh.number}", lambda sc=sc, sh=sh: self.generate_shot(project, sc, sh, force)))
                jobs.append((f"voice {sh.number}", lambda sh=sh: self.generate_dialogue(project, sh)))
                jobs.append((f"sfx {sh.number}", lambda sh=sh: self.generate_sfx(project, sh)))
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=max(1, settings.workers)) as pool:
            futs = {pool.submit(fn): label for label, fn in jobs}
            for i, f in enumerate(as_completed(futs), 1):
                try:
                    f.result()
                except Exception as e:
                    log.exception("generation failed: %s", futs[f])
                    errors.append(f"{futs[f]}: {str(e)[:300]}")
                progress(0.75 * i / len(jobs), f"Generated {futs[f]}")
                if i % 10 == 0:
                    self.store.save(project)
        self.store.save(project)
        return errors

    # ================================================================ edit + mix + export
    def render(self, project: Project, scene_id: Optional[str] = None, progress: Optional[Progress] = None,
               force: bool = False) -> RenderOutput:
        progress = progress or (lambda f, m: None)
        scenes = [s for s in project.scenes if not scene_id or s.id == scene_id]
        if not scenes or not any(s.shots for s in scenes):
            raise ValueError("nothing to render")
        errors = self.produce(project, scenes, progress, force)
        missing = [sh.number for sc in scenes for sh in sc.shots
                   if not (p := self.store.abspath(project.id, sh.clip_path)) or not p.exists()]
        if missing:
            raise RuntimeError(f"shots failed to generate: {missing[:20]}; errors: {errors[:5]}")
        st = project.bible.style
        entries, total = build_timeline(scenes)
        out_dir = self.store.media(project.id, "renders")
        tag = f"{'scene_' + str(scenes[0].number) if scene_id else 'film'}_{digest(project.updated, total)[:6]}"
        work = Path(tempfile.mkdtemp(prefix="render_", dir=out_dir))

        progress(0.78, "Editing picture")
        picture = self._edit_picture(project, entries, work, st.width, st.height, st.fps)
        progress(0.86, "Mixing sound")
        mix = self._mix(project, entries, total, work)
        srt = out_dir / f"{tag}.srt"
        self._write_srt(project, entries, srt)
        edl = out_dir / f"{tag}.edl"
        self._write_edl(project, entries, edl, st.fps)
        progress(0.92, "Color grade, master & export")
        final = out_dir / f"{tag}.mp4"
        self._master(project, picture, mix, srt, total, final)
        for f in work.iterdir():
            f.unlink()
        work.rmdir()
        r = RenderOutput(video_path=self.store.rel(project.id, final), subtitles_path=self.store.rel(project.id, srt),
                         edl_path=self.store.rel(project.id, edl), duration=round(probe_duration(final), 2),
                         scope="film" if not scene_id else f"scene {scenes[0].number}")
        project.renders.insert(0, r)
        self.store.save(project)
        progress(1.0, "Done")
        return r

    def _edit_picture(self, project: Project, entries: list[Entry], work: Path, W: int, H: int, fps: int) -> Path:
        # Split the timeline into chunks at hard cuts; each chunk is one xfade chain.
        chunks: list[list[Entry]] = []
        for e in entries:
            if not chunks or e.transition not in XFADE:
                chunks.append([e])
            else:
                chunks[-1].append(e)
        files = []
        for ci, chunk in enumerate(chunks):
            args: list = []
            fl: list[str] = []
            for i, e in enumerate(chunk):
                args += ["-i", self.store.abspath(project.id, e.shot.clip_path)]
                fl.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},"
                          f"tpad=stop_mode=clone:stop_duration={e.duration},trim=duration={e.duration},"
                          f"setpts=PTS-STARTPTS,format=yuv420p,setsar=1[v{i}]")
            last, length = "v0", chunk[0].duration
            for i, e in enumerate(chunk[1:], 1):
                off = round(length - e.tdur, 3)
                fl.append(f"[{last}][v{i}]xfade=transition={XFADE[e.transition]}:duration={e.tdur}:offset={off}[x{i}]")
                last, length = f"x{i}", off + e.duration
            out = work / f"chunk_{ci:05}.mp4"
            script = work / f"chunk_{ci:05}.txt"
            script.write_text(";".join(fl))
            run([*args, "-filter_complex_script", script, "-map", f"[{last}]", *VIDEO_ENC, "-r", fps, "-an", out])
            files.append(out)
        lst = work / "concat.txt"
        lst.write_text("".join(f"file '{f.name}'\n" for f in files))
        picture = work / "picture.mp4"
        run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", picture])
        return picture

    def _events(self, project: Project, entries: list[Entry]) -> list[AudioEvent]:
        m = project.mix
        ev: list[AudioEvent] = []
        seen_scenes: set[str] = set()
        for e in entries:
            if e.scene.id not in seen_scenes:
                seen_scenes.add(e.scene.id)
                if e.scene.music_path and not m.music.mute:
                    ev.append(AudioEvent(self.store.abspath(project.id, e.scene.music_path), e.start, m.music.volume,
                                         "music", fade=1.0))
            for line in e.shot.dialogue:
                if line.audio_path and not m.dialogue.mute:
                    ev.append(AudioEvent(self.store.abspath(project.id, line.audio_path), e.start + line.offset,
                                         m.dialogue.volume, "dialogue"))
            for cue in e.shot.sounds:
                if cue.audio_path and not m.sfx.mute:
                    ev.append(AudioEvent(self.store.abspath(project.id, cue.audio_path), e.start + cue.offset,
                                         m.sfx.volume * cue.volume, "sfx", fade=0.3))
        return ev

    def _mix(self, project: Project, entries: list[Entry], total: float, work: Path) -> Path:
        """Windowed numpy mixer: scales to feature length with bounded memory."""
        m = project.mix
        events = self._events(project, entries)
        n_total = int(np.ceil(total * SR))
        win = 60 * SR
        depth = min(0.92, m.duck_amount / 10.0) if m.ducking else 0.0
        cache: dict[Path, np.ndarray] = {}
        raw = work / "mix.f32"
        with open(raw, "wb") as fh:
            for w0 in range(0, n_total, win):
                w1 = min(n_total, w0 + win)
                stems = {k: np.zeros(w1 - w0, np.float32) for k in ("dialogue", "music", "sfx")}
                for ev in events:
                    s0 = int(ev.start * SR)
                    if ev.path not in cache:
                        a = load_audio(ev.path)
                        if ev.fade:
                            k = min(len(a) // 2, int(ev.fade * SR))
                            if k:
                                ramp = np.linspace(0, 1, k, dtype=np.float32)
                                a[:k] *= ramp
                                a[-k:] *= ramp[::-1]
                        cache[ev.path] = a
                        if len(cache) > 64:
                            cache.pop(next(iter(cache)))
                    a = cache[ev.path]
                    s1 = s0 + len(a)
                    lo, hi = max(s0, w0), min(s1, w1)
                    if lo < hi:
                        stems[ev.stem][lo - w0:hi - w0] += ev.gain * a[lo - s0:hi - s0]
                if depth:
                    env = movavg(np.abs(stems["dialogue"]), int(0.05 * SR))
                    gain = 1.0 - depth * np.clip(env / 0.03, 0, 1)
                    stems["music"] *= movavg(gain, int(0.25 * SR))
                mixed = stems["dialogue"] + stems["music"] + stems["sfx"]
                np.clip(mixed, -1, 1, out=mixed)
                fh.write(mixed.astype(np.float32).tobytes())
        return raw

    def _write_srt(self, project: Project, entries: list[Entry], path: Path) -> None:
        out, n = [], 0
        for e in entries:
            for line in e.shot.dialogue:
                c = project.bible.character(line.character_id)
                t0 = e.start + line.offset
                t1 = t0 + (line.duration or 2.0)
                n += 1
                out.append(f"{n}\n{fmt_srt(t0)} --> {fmt_srt(t1)}\n{(c.name.upper() + ': ') if c else ''}{line.text}\n")
        path.write_text("\n".join(out))

    def _write_edl(self, project: Project, entries: list[Entry], path: Path, fps: int) -> None:
        lines = [f"TITLE: {project.bible.title[:60]}", "FCM: NON-DROP FRAME", ""]
        for i, e in enumerate(entries, 1):
            kind = "C       " if e.transition not in XFADE else f"D    {int(e.tdur * fps):03}"
            src_in, src_out = fmt_tc(0, fps), fmt_tc(e.duration, fps)
            rec_in, rec_out = fmt_tc(3600 + e.start, fps), fmt_tc(3600 + e.start + e.duration, fps)
            lines.append(f"{i:03}  {('S' + e.shot.number)[:8]:<8} V     {kind} {src_in} {src_out} {rec_in} {rec_out}")
            lines.append(f"* FROM CLIP NAME: {Path(e.shot.clip_path or '').name}")
            lines.append(f"* SCENE {e.scene.number}: {e.scene.heading}")
        path.write_text("\n".join(lines) + "\n")

    def _master(self, project: Project, picture: Path, mix: Path, srt: Path, total: float, out: Path) -> None:
        st, g, m = project.bible.style, project.grade, project.mix
        preset = st.grade if g.preset == "auto" else g.preset
        vf = [GRADES.get(preset, "null")]
        if st.lut_path and Path(st.lut_path).exists():
            vf.append(f"lut3d='{ffpath(st.lut_path)}'")
        if g.vignette:
            vf.append("vignette=PI/6")
        if g.grain and "grain" in st.film_stock.lower():
            vf.append("noise=alls=5:allf=t")
        vf.append("fade=t=in:st=0:d=0.8")   # films open from black and end on black
        vf.append(f"fade=t=out:st={max(0.0, total - 1.0):.3f}:d=1.0")
        if m.burn_subtitles and srt.stat().st_size:
            vf.append(f"subtitles='{ffpath(srt)}':force_style='FontSize=18,Outline=1'")
        if g.letterbox and st.width / st.height > 16 / 9 + 0.01:
            ph = int(round(st.width * 9 / 16 / 2) * 2)
            vf.append(f"pad={st.width}:{ph}:0:(oh-ih)/2:black")
        vf.append("format=yuv420p")
        af = f"loudnorm=I={m.loudness_lufs}:TP=-1.5:LRA=11,aresample={SR},aformat=channel_layouts=stereo"
        run(["-i", picture, "-f", "f32le", "-ar", SR, "-ac", 1, "-i", mix, "-map", "0:v", "-map", "1:a",
             "-vf", ",".join(vf), "-af", af, *VIDEO_ENC, "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}",
             "-movflags", "+faststart", out])
