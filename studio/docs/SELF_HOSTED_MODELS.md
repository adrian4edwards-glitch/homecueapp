# Self-hosted model stack

Everything below is open-weight and runs on hardware you control. Check each model's license
before commercial use: several open video and voice models carry non-commercial or custom terms.

| Department | Suggested models | Server | Engine variable |
|---|---|---|---|
| Writers' room (LLM) | Llama 3.x 70B / Qwen 2.5 72B (quality) or 8B-class (speed) | Ollama, vLLM, llama.cpp: any OpenAI-compatible `/v1/chat/completions` | `CUESTUDIO_LLM_URL`, `CUESTUDIO_LLM_MODEL` |
| Keyframes / character sheets | FLUX.1 / SDXL + IP-Adapter / face-ID | ComfyUI | (inside your workflow) |
| Video (live action, 3D, cartoon) | Wan 2.x (T2V / I2V), HunyuanVideo, LTX-Video, CogVideoX | ComfyUI | `CUESTUDIO_COMFY_URL`, `CUESTUDIO_COMFY_WORKFLOW` |
| Lip-sync (optional pass) | LatentSync / MuseTalk-style nodes | ComfyUI (same workflow) | n/a |
| Voice (TTS / cloning) | Kokoro, XTTS-v2, F5-TTS, Piper | Kokoro-FastAPI / openedai-speech: OpenAI-compatible `/v1/audio/speech` | `CUESTUDIO_TTS_URL`, `CUESTUDIO_TTS_MODEL` |
| Music + SFX | MusicGen, Stable Audio Open, AudioGen | `engine/servers/audio_server.py` | `CUESTUDIO_MUSIC_URL` |

## Minimal GPU setup

1. **LLM:** `docker compose --profile ai up -d ollama && docker compose exec ollama ollama pull llama3.1:8b`,
   then `CUESTUDIO_LLM_URL=http://ollama:11434/v1`.
2. **Video:** install ComfyUI on a 24 GB+ GPU (48–80 GB for the larger video models at 720p),
   install your chosen model's nodes and weights, build a workflow, and export it in API format
   to `engine/workflows/video_api.json` with the tokens described in `engine/workflows/README.md`.
   Set `CUESTUDIO_COMFY_URL=http://<gpu-host>:8188`.
3. **Voice:** run an OpenAI-compatible TTS server and set each character's `voice_id` in the
   Story Bible to one of its voices (or a cloned voice).
4. **Music:** `pip install transformers torch scipy && uvicorn servers.audio_server:app --port 8890`.

Each department is independent. Connect them one at a time; whatever isn't connected keeps
using the built-in previz backend. `GET /api/health` shows what each department is using.

## Rough cost model

Per finished minute at 720p with a ~10 B-parameter-class video model on a single high-end GPU,
expect tens of minutes to a few hours of GPU time, depending on the model, steps and how many
takes you generate. Budget for 2–4 takes per shot. Rendering in previz first and only sending
approved shots to the GPU is the biggest cost saver; the studio is built around that workflow.
