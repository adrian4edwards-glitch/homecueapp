"""Reference self-hosted music + SFX server for HomeCue Studio (GPU recommended).

    pip install fastapi uvicorn transformers torch scipy numpy
    uvicorn servers.audio_server:app --host 0.0.0.0 --port 8890
    export CUESTUDIO_MUSIC_URL=http://<host>:8890

Contract used by the engine: POST /generate {"prompt", "duration", "kind": "music"|"sfx"} -> WAV bytes.
Uses MusicGen for music and AudioGen-style prompting for sfx via the same model family. Swap in
Stable Audio Open or any model you prefer - only this file changes.
"""
import io
import os

import numpy as np
import scipy.io.wavfile
import torch
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel
from transformers import AutoProcessor, MusicgenForConditionalGeneration

MODEL = os.environ.get("MUSIC_MODEL", "facebook/musicgen-small")
device = "cuda" if torch.cuda.is_available() else "cpu"
processor = AutoProcessor.from_pretrained(MODEL)
model = MusicgenForConditionalGeneration.from_pretrained(MODEL).to(device)
SR = model.config.audio_encoder.sampling_rate
app = FastAPI(title="HomeCue audio server")


class Req(BaseModel):
    prompt: str
    duration: float = 10.0
    kind: str = "music"


def _segment(prompt: str, seconds: float) -> np.ndarray:
    inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)
    with torch.no_grad():
        audio = model.generate(**inputs, max_new_tokens=int(min(seconds, 30) * 50) + 4)
    return audio[0, 0].float().cpu().numpy()


@app.post("/generate")
def generate(req: Req) -> Response:
    prompt = req.prompt if req.kind == "music" else f"sound effect, foley, no music: {req.prompt}"
    target = int(max(0.5, req.duration) * SR)
    out = _segment(prompt, req.duration)
    xf = int(1.0 * SR)
    while len(out) < target:  # MusicGen tops out ~30s: extend with crossfaded segments
        nxt = _segment(prompt, min(30, (target - len(out)) / SR + 1.5))
        ramp = np.linspace(0, 1, min(xf, len(nxt), len(out)))
        k = len(ramp)
        out = np.concatenate([out[:-k], out[-k:] * (1 - ramp) + nxt[:k] * ramp, nxt[k:]])
    out = out[:target]
    buf = io.BytesIO()
    scipy.io.wavfile.write(buf, SR, (out / (np.abs(out).max() + 1e-6) * 0.9).astype(np.float32))
    return Response(buf.getvalue(), media_type="audio/wav")
