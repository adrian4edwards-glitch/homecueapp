# Lovable brief: HomeCue Studio product frontend

Paste everything below the line into a new Lovable project. It builds the customer-facing
app (auth, teams, polished UI) on top of the HomeCue Studio engine API. The engine does all
AI work on your own servers, so the Lovable app never needs AI credits at runtime.

---

Build **HomeCue Studio**, a premium dark-themed web app for producing AI films. It is a
frontend for an existing REST API (the "engine"). Do not use any built-in AI features;
all generation happens in the engine.

**Config:** read the engine base URL from an env var `VITE_ENGINE_URL` (default
`http://localhost:8000`). Media URLs are `${ENGINE}/files/{projectId}/{relativePath}`.

**Auth & data:** Supabase auth (email + Google). Table `productions(id uuid, user_id, engine_project_id text, title text, created_at)` with RLS so users only see their own rows.

**Pages**
1. **New production:** large prompt box, medium picker (cards: Live action, 3D feature
   animation, 2D cartoon, Anime, Stop-motion, Motion graphics), genre (auto), runtime slider
   (0.5–180 min), aspect ratio chips, optional cast lines "Name: look". Submit →
   `POST /api/projects` → save row → go to the production.
2. **Production workspace** with tabs:
   - **Story Bible:** editable cast cards (name, role, description, wardrobe, personality, arc,
     mannerisms, voice id/pitch/rate, reference image upload via
     `POST /api/projects/{id}/characters/{cid}/reference?filename=` with the raw file body),
     locations, props, look & tone (palette color pickers, grade select). Save →
     `PUT /api/projects/{id}/bible` with the whole bible object.
   - **Storyboard:** scenes as rows, shots as cards with hover-play video thumbnails; edit
     shot fields with `PATCH /api/projects/{id}/shots/{shotId}`; Generate →
     `POST .../shots/{shotId}/generate` (returns `job_id`); Approve = PATCH `{status:"approved"}`;
     drag-reorder shots → `PUT /api/projects/{id}/scenes/{sceneId}/order` (array of shot ids);
     drag-reorder scenes → `PUT /api/projects/{id}/order`; add scene → `POST /api/projects/{id}/scenes`.
   - **Editor:** NLE-style timeline from `GET /api/projects/{id}/timeline` with 4 tracks
     (picture, dialogue, music, sfx), zoom slider, playhead, clip inspector (trim duration,
     transition) and a program monitor that plays clips in sequence.
   - **Audio:** mixer with stem faders and mutes, ducking toggle and depth, loudness target
     select → `PUT /api/projects/{id}/mix`; picture finishing → `PUT /api/projects/{id}/grade`.
   - **Continuity:** list from `GET /api/projects/{id}/continuity` grouped by severity, each
     linking to its shot.
   - **Render:** "Render film" → `POST /api/projects/{id}/render` `{}`; poll
     `GET /api/jobs/{jobId}` every second and show progress and message; list
     `project.renders` with a player and MP4/SRT/EDL downloads; screenplay download
     `GET /api/projects/{id}/screenplay`.
3. **Library:** grid of the user's productions with the latest render's thumbnail.

**Design:** cinematic and minimal, near-black background, amber accent (#f5a524), violet
secondary (#7c5cff), Inter font, generous spacing, subtle film-grain texture in the header,
fully responsive down to 390 px. Show a status pill on every shot
(planned/generating/ready/approved/failed). Show API errors (`detail` field) as toasts.
A 409 response means "production is rendering"; disable editing and show a banner.
