# HomeCue Studio

A self-hosted AI film studio. You type a prompt; it develops, shoots, edits, mixes and
masters **one finished film** with consistent characters, wardrobe, locations, palette,
tone and camera language from the first shot to the last.

```
prompt ─► Writers' room ─► Story Bible ─► Screenplay ─► Cinematographer ─► Shot list
                              (locked identities,          (coverage, 180° rule,
                               wardrobe, palette, tone)     lenses, moves, blocking)
                                                                  │
          ┌──────────── Prompt compiler (continuity injected into every shot) ◄┘
          ▼
   Camera dept ─ clips      Voice dept ─ dialogue      Music dept ─ score      SFX dept
          └──────────────┬──────────────┴───────────────────┴────────────────────┘
                         ▼
     Edit bay (timeline, cuts, dissolves/wipes) ─► Mix stage (ducking, LUFS) ─►
     Finishing (grade, LUT, grain, letterbox, subtitles) ─► MP4 + SRT + EDL + screenplay
```

**No AI credits from anyone.** Every AI department talks to a model *you* host (open-weight
models on your own GPUs). With no models connected, every department falls back to a
built-in "previz" backend, so the whole studio runs on a laptop CPU: you get a fully
timed, edited and mixed **animatic** of the film (staging, camera moves, dialogue timing,
score bed, sound effects) that you can then upgrade shot-by-shot to final pixels.

## Quick start

```bash
cd studio/engine
pip install -r requirements.txt          # needs ffmpeg on PATH
uvicorn cuestudio.api:app --port 8000
# open http://localhost:8000  (API docs at /docs)
```

or `docker compose up engine` from `studio/`.

Run the tests: `cd studio/engine && pytest` (7 end-to-end tests, ~1 min).

## What's in the studio

| Area | What it does |
|---|---|
| **Story Bible** | Characters (locked physical description, wardrobe, personality, motivation, arc, mannerisms, voice, identity reference images, LoRA, seed), locations (set dressing / mise-en-scène, lighting), props, and the global look: medium, palette, tone, lens package, film stock, grade, score style. |
| **Screenplay & Shots** | Beat-sheet structure scaled from 30 seconds to 240 minutes. Every scene gets coverage designed by the cinematographer: establishing shot, master, OTS/MCU/CU dialogue coverage, reactions, prop inserts, closing shot. Every shot is editable: size, angle, camera move, lens, duration, transition, action, blocking, dialogue. Generate, approve (lock), and swap takes. |
| **Editor** | Multi-track timeline (picture, dialogue, music, SFX), clip preview, trim, transitions (cut, dissolve, fade to black/white, wipes, slide, circle). |
| **Audio Studio** | Per-stem volume/mute, sidechain ducking of score under dialogue, loudness targets (streaming / web / broadcast), voice auditioning. |
| **Continuity** | Automated script supervisor: identity locks, wardrobe changes, 180° rule, jump cuts, dialogue that overruns its shot, broken references. |
| **Render & Export** | Film or single-scene renders, MP4 master, SRT subtitles, CMX3600 EDL (open in Premiere / Resolve / Avid), screenplay text, and a **training dataset export** of approved shots. |

Supported mediums: photoreal live action, 3D feature animation, 2D cartoon, anime,
stop-motion, motion graphics. Aspect ratios: 2.39:1, 1.85:1, 16:9, 9:16, 1:1, 4:3.

## Plugging in your own models

Set these and restart (details: [docs/SELF_HOSTED_MODELS.md](docs/SELF_HOSTED_MODELS.md)):

| Variable | Department | Example |
|---|---|---|
| `CUESTUDIO_LLM_URL`, `CUESTUDIO_LLM_MODEL` | Writers' room | Ollama / vLLM / llama.cpp: `http://localhost:11434/v1` |
| `CUESTUDIO_COMFY_URL`, `CUESTUDIO_COMFY_WORKFLOW` | Camera | ComfyUI running Wan 2.x / HunyuanVideo / LTX-Video |
| `CUESTUDIO_TTS_URL`, `CUESTUDIO_TTS_MODEL` | Voice | Kokoro-FastAPI, XTTS / F5-TTS servers (OpenAI-compatible) |
| `CUESTUDIO_MUSIC_URL` | Music + SFX | `servers/audio_server.py` (MusicGen) |
| `CUESTUDIO_DATA`, `CUESTUDIO_WORKERS` | Storage / parallelism | `/data`, `4` |

## More

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how consistency works, the pipeline, and the roadmap to your own models
- [docs/SELF_HOSTED_MODELS.md](docs/SELF_HOSTED_MODELS.md): GPU model stack and setup
- [docs/LOVABLE_FRONTEND_PROMPT.md](docs/LOVABLE_FRONTEND_PROMPT.md): paste into Lovable to build the polished product UI on top of this engine
