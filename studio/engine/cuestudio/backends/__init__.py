"""Pluggable generation backends.

Each department (camera, voice, music, sfx) has:
  * a self-hosted model backend (ComfyUI / OpenAI-compatible TTS / music server)
  * a built-in "previz" backend that needs no GPU, so the full pipeline -
    planning, generation, editing, mixing and export - always runs.
"""
from ..config import settings
from .audio import HttpMusic, HttpTTS, MusicBackend, PrevizMusic, PrevizSfx, PrevizTTS, SfxBackend, TTSBackend
from .video import ComfyUIVideo, PrevizVideo, VideoBackend


def video_backend() -> VideoBackend:
    return ComfyUIVideo(settings.comfy_url, settings.comfy_workflow) if settings.comfy_url else PrevizVideo()


def tts_backend() -> TTSBackend:
    return HttpTTS(settings.tts_url, settings.tts_model) if settings.tts_url else PrevizTTS()


def music_backend() -> MusicBackend:
    return HttpMusic(settings.music_url) if settings.music_url else PrevizMusic()


def sfx_backend() -> SfxBackend:
    return HttpMusic(settings.music_url, kind="sfx") if settings.music_url else PrevizSfx()  # type: ignore[return-value]


def describe() -> dict:
    return {
        "video": video_backend().name, "tts": tts_backend().name, "music": music_backend().name,
        "sfx": sfx_backend().name, "llm": f"local:{settings.llm_model}" if settings.llm_url else "built-in writer",
    }
