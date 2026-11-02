"""Runtime configuration (environment variables).

Every AI component points at a model *you* host. Nothing here calls a paid,
credit-metered third-party API.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(_env("CUESTUDIO_DATA", str(Path.cwd() / "data"))).resolve()
        # Writers' room: any OpenAI-compatible server you run yourself
        # (Ollama, vLLM, llama.cpp server, LM Studio, TGI...).
        self.llm_url = _env("CUESTUDIO_LLM_URL")            # e.g. http://localhost:11434/v1
        self.llm_model = _env("CUESTUDIO_LLM_MODEL", "llama3.1:8b")
        # Camera department: a ComfyUI server running open-weight video models
        # (Wan 2.x, HunyuanVideo, LTX-Video, CogVideoX, ...).
        self.comfy_url = _env("CUESTUDIO_COMFY_URL")        # e.g. http://localhost:8188
        self.comfy_workflow = _env("CUESTUDIO_COMFY_WORKFLOW", "workflows/video_api.json")
        # Voice department: OpenAI-compatible /v1/audio/speech server you host
        # (Kokoro-FastAPI, openedai-speech w/ XTTS, F5-TTS servers, ...).
        self.tts_url = _env("CUESTUDIO_TTS_URL")
        self.tts_model = _env("CUESTUDIO_TTS_MODEL", "tts-1")
        # Music department: self-hosted MusicGen / Stable Audio Open HTTP wrapper.
        self.music_url = _env("CUESTUDIO_MUSIC_URL")
        self.workers = int(_env("CUESTUDIO_WORKERS", "2"))

    @property
    def projects_dir(self) -> Path:
        p = self.data_dir / "projects"
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
