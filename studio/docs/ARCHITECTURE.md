# Architecture

## The core idea: one source of truth, compiled into every shot

Today's video models can't hold a character or a story together across a 90-minute film
on their own. Each clip is generated in isolation and drifts. HomeCue Studio doesn't ask
the model to remember anything. It keeps the film's memory itself and **re-states it in
every single generation request**:

1. **Story Bible** (`models.py`): canonical, never-changing records for each character
   (physical description, wardrobe, mannerisms, voice, identity refs, LoRA, seed), each
   location (layout, set dressing, lighting, seed), each prop, and the global style guide
   (medium, look, palette, tone, lens package, film stock, grade).
2. **Prompt compiler** (`prompt_compiler.py`) turns a shot into a `GenerationRequest`:
   camera language + global look + location + *every character in frame with their
   locked description and current wardrobe* + action + blocking + props + set + lighting
   + mood + palette, plus identity reference images, LoRAs and a deterministic seed.
   Changing a wardrobe in the bible changes every affected prompt; the cache key changes,
   so exactly those shots regenerate on the next render.
3. **Cinematographer** (`cinematography.py`) applies one consistent camera grammar to
   every scene: establishing → master → shot/reverse-shot → reactions → inserts →
   closing. It also assigns screen direction so the 180° line is never crossed.
4. **Script supervisor** (`continuity.py`) audits the whole film for continuity breaks.

## Consistency levers, from cheapest to strongest

| Lever | Where | Effect |
|---|---|---|
| Locked text descriptions + wardrobe in every prompt | prompt compiler | baseline identity/costume consistency |
| Deterministic seeds per character / location / shot | planner, cinematography | repeatable looks, reproducible takes |
| Identity reference images → IP-Adapter / face-ID / image-to-video keyframes | `{{ref_image}}` in ComfyUI workflow | strong face/costume lock |
| Per-character LoRA trained on approved frames | `Character.lora` → `{{lora}}` | strongest identity lock |
| Approve/lock shots, swap takes | API + UI | humans pick the best take; locked shots never regenerate |
| Dataset export of approved shots | `/api/projects/{id}/dataset` | data flywheel for fine-tuning (below) |

## Pipeline

```
POST /api/projects             planner.py         prompt → bible → beats → scenes (LLM or built-in)
                               cinematography.py  scenes → shots
POST /api/projects/{id}/render studio.py
   produce()                   parallel: shots (video), dialogue (TTS), score (music), cues (sfx)
                               content-addressed cache: unchanged assets are never regenerated
   build_timeline()            global timeline; overlapping transitions shorten it correctly
   _edit_picture()             splits at hard cuts → per-chunk xfade chains → concat (scales to features)
   _mix()                      windowed numpy mixer (60 s windows, bounded RAM for 2-hour films),
                               dialogue-keyed ducking of the score
   _master()                   grade preset / LUT, vignette, grain, fades, subtitles, letterbox,
                               EBU R128 loudness normalisation, H.264/AAC
   exports                     MP4, SRT, CMX3600 EDL
```

Long jobs run on a background runner (`jobs.py`); the UI polls `/api/jobs/{id}`. While a
project is rendering, writes to it return 409 so edits can't be lost.

## Backends (the "departments")

`backends/__init__.py` selects, per department, either a self-hosted model backend or the
built-in previz backend. Adding a new model is one class with one method
(`generate` / `speak` / `compose`).

## "Its own AI": the honest roadmap

You asked for an app whose AI is its own and doesn't run on anyone's credits. That's the
right goal. Here is the realistic route to it:

**Phase 1: own the runtime (this codebase, now).** Every department runs on open-weight
models you host. No per-generation fees. Your cost becomes GPU time. Lovable and Claude
help you *build* the app; they are not in the runtime path and can't train a video model.

**Phase 2: own the consistency (weeks).** Add per-character LoRA training: render a
character sheet from the bible, have a human approve 15–30 frames, train a LoRA
(kohya / diffusers / musubi-tuner style scripts on one GPU, ~1 hour), and write its name to
`Character.lora`. Same for locations. This is where "same actor in every shot" becomes
dependable.

**Phase 3: own the model (months, real capital).** Fine-tune an open video base model on
(a) properly licensed footage and (b) the approved-shot dataset this app exports. Training
a frontier video model *from scratch* takes thousands of GPUs and a large licensed corpus.
Fine-tuning an existing open model on your own data is the achievable path to a
proprietary model, and every approved shot your users make feeds it.

**Known limits today.** Open models produce roughly 5–10 s per clip at 720p. That's why the
studio is shot-based and assembles the film in the edit bay, which is also how real films
are made. Lip-sync to generated dialogue needs a dedicated lip-sync model pass
(e.g. a LatentSync / MuseTalk-style node in the ComfyUI workflow). The best Hollywood- or
feature-animation-grade results still come from generating multiple takes and having a
human pick the best one, which the approve/takes workflow is built for.

## Scaling to production

- Run several ComfyUI GPU workers behind a queue. `CUESTUDIO_WORKERS` controls
  parallel generations per engine.
- Move `ProjectStore` to Postgres + object storage (S3/R2) when you go multi-user; the API
  surface stays the same.
- Put auth, billing and teams in the product frontend (Lovable + Supabase); the engine
  stays a stateless-ish internal service.
