"""Client for a self-hosted, OpenAI-compatible chat model."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from .config import settings


class LocalLLM:
    def __init__(self, url: Optional[str] = None, model: Optional[str] = None, timeout: float = 300):
        self.url = (url if url is not None else settings.llm_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.url)

    def chat(self, system: str, user: str, temperature: float = 0.8) -> str:
        r = httpx.post(
            f"{self.url}/chat/completions",
            json={
                "model": self.model,
                "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def chat_json(self, system: str, user: str, temperature: float = 0.7) -> Any:
        text = self.chat(system + "\nRespond with JSON only. No prose, no markdown fences.", user, temperature)
        return extract_json(text)


def extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON found in model output")
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    return json.loads(text[start : end + 1])
