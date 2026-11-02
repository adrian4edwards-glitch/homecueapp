"""Voice, music and sound-effects backends."""
from __future__ import annotations

from pathlib import Path

import httpx
import numpy as np

from ..ffmpeg import SR, save_audio
from ..models import digest

MINOR_WORDS = ("dark", "tense", "dread", "somber", "devastat", "sad", "menac", "unsettl", "conflict", "claustro")


class TTSBackend:
    name = "base"

    def speak(self, text: str, voice: dict, out_path: Path, emotion: str = "neutral") -> Path:
        raise NotImplementedError


class MusicBackend:
    name = "base"

    def compose(self, prompt: str, duration: float, out_path: Path) -> Path:
        raise NotImplementedError


class SfxBackend(MusicBackend):
    pass


# --------------------------------------------------------------------------- previz
class PrevizTTS(TTSBackend):
    """Speech-timed guide track: a voiced, syllable-rhythmic tone per character
    pitch. Correct timing for editing and ducking; swap in a real TTS for voices."""

    name = "previz (guide voice)"

    def speak(self, text: str, voice: dict, out_path: Path, emotion: str = "neutral") -> Path:
        words = max(1, len(text.split()))
        rate = float(voice.get("rate", 1.0)) or 1.0
        dur = words / (2.6 * rate) + 0.4
        t = np.arange(int(dur * SR)) / SR
        f0 = 150.0 * float(voice.get("pitch", 1.0))
        vibrato = 1 + 0.03 * np.sin(2 * np.pi * 0.8 * t + len(text) % 7)
        phase = 2 * np.pi * np.cumsum(f0 * vibrato) / SR
        tone = sum(np.sin(k * phase) / k for k in range(1, 6))
        syll = np.clip(np.sin(2 * np.pi * 2.6 * rate * t * 1.5), 0, None) ** 0.6
        env = np.minimum(1, np.minimum(t / 0.05, (dur - t) / 0.08))
        save_audio(0.22 * tone * syll * env, out_path)
        return out_path


def _ambient_pad(prompt: str, duration: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    minor = any(w in prompt.lower() for w in MINOR_WORDS)
    root = 110.0 * 2 ** (rng.integers(0, 7) / 12)
    chord = [1, 1.189 if minor else 1.26, 1.498, 2.0]
    t = np.arange(int(duration * SR)) / SR
    sig = sum(np.sin(2 * np.pi * root * r * t + rng.random() * 6) * (0.6 if i == 0 else 0.35)
              for i, r in enumerate(chord))
    sig *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.12 * t)
    fade = min(2.0, duration / 3)
    env = np.minimum(1, np.minimum(t / fade, (duration - t) / fade))
    return 0.12 * sig * env


class PrevizMusic(MusicBackend):
    name = "previz (mood pad)"

    def compose(self, prompt: str, duration: float, out_path: Path) -> Path:
        save_audio(_ambient_pad(prompt, max(0.5, duration), int(digest(prompt), 16) % 2**32), out_path)
        return out_path


class PrevizSfx(SfxBackend):
    name = "previz (procedural sfx)"

    def compose(self, prompt: str, duration: float, out_path: Path) -> Path:
        n = int(max(0.2, duration) * SR)
        rng = np.random.default_rng(int(digest(prompt), 16) % 2**32)
        white = rng.standard_normal(n).astype(np.float32)
        p = prompt.lower()
        if any(w in p for w in ("rain", "wind", "ocean", "wave", "ambience", "tone", "room", "crowd", "traffic")):
            sig = np.cumsum(white)                    # brown-ish noise bed
            sig -= np.convolve(sig, np.ones(2000) / 2000, mode="same")
            sig = sig / (np.abs(sig).max() + 1e-6) * 0.3
        else:                                         # percussive hit / foley
            t = np.arange(n) / SR
            sig = white * np.exp(-t * 18) * 0.6
        save_audio(sig, out_path)
        return out_path


# --------------------------------------------------------------------------- self-hosted models
class HttpTTS(TTSBackend):
    """Any OpenAI-compatible speech server you host (Kokoro-FastAPI, openedai-speech
    with XTTS/Piper, F5-TTS servers...). voice_id maps to the server's voice name or
    a cloned reference voice."""

    def __init__(self, url: str, model: str):
        self.url, self.model = url.rstrip("/"), model
        self.name = f"tts @ {self.url}"

    def speak(self, text: str, voice: dict, out_path: Path, emotion: str = "neutral") -> Path:
        r = httpx.post(f"{self.url}/audio/speech", json={"model": self.model, "input": text,
                       "voice": voice.get("voice_id", "default"), "response_format": "wav",
                       "speed": voice.get("rate", 1.0)}, timeout=300)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        return out_path


class HttpMusic(SfxBackend):
    """Self-hosted MusicGen / AudioGen / Stable Audio Open wrapper.
    Contract: POST {url}/generate {"prompt", "duration", "kind"} -> audio bytes.
    See servers/audio_server.py for a reference implementation."""

    def __init__(self, url: str, kind: str = "music"):
        self.url, self.kind = url.rstrip("/"), kind
        self.name = f"{kind} @ {self.url}"

    def compose(self, prompt: str, duration: float, out_path: Path) -> Path:
        r = httpx.post(f"{self.url}/generate", json={"prompt": prompt, "duration": duration, "kind": self.kind},
                       timeout=1800)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        return out_path
