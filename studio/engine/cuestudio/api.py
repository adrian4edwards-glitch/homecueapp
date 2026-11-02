"""HomeCue Studio REST API.

Run:  uvicorn cuestudio.api:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs   Studio UI: http://localhost:8000/
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from . import backends
from .cinematography import SceneDraft, design_coverage
from .config import settings
from .continuity import check_project
from .jobs import JobRunner
from .models import (CreateRequest, DialogueLine, GradeSettings, MixSettings, Project, Scene, Shot, Status,
                     StoryBible)
from .planner import Planner
from .prompt_compiler import compile_shot
from .storage import ProjectStore
from .studio import Studio, build_timeline

app = FastAPI(title="HomeCue Studio Engine", version="0.1.0",
              description="Self-hosted AI film studio: story bible, screenplay, shot design, generation, edit, mix.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

store = ProjectStore()
studio = Studio(store)
runner = JobRunner(workers=1)
STATIC = Path(__file__).parent / "static"


def load(pid: str) -> Project:
    try:
        return store.load(pid)
    except KeyError:
        raise HTTPException(404, "project not found")


def writable(pid: str) -> Project:
    job = runner.active_for(pid)
    if job:
        raise HTTPException(409, f"project is busy ({job.kind} job {job.id}); wait for it to finish")
    return load(pid)


def merge(model: BaseModel, patch: dict) -> Any:
    return type(model).model_validate({**model.model_dump(), **patch})


# ------------------------------------------------------------------ system
@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "backends": backends.describe(), "data_dir": str(settings.data_dir)}


# ------------------------------------------------------------------ projects
@app.get("/api/projects")
def list_projects() -> list[dict]:
    return store.list()


@app.post("/api/projects")
def create_project(req: CreateRequest) -> Project:
    if not req.prompt.strip():
        raise HTTPException(400, "prompt is required")
    if req.target_minutes <= 0 or req.target_minutes > 240:
        raise HTTPException(400, "target_minutes must be between 0 and 240")
    return store.save(Planner().create_project(req))


@app.get("/api/projects/{pid}")
def get_project(pid: str) -> Project:
    return load(pid)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str) -> dict:
    writable(pid)
    store.delete(pid)
    return {"deleted": pid}


@app.put("/api/projects/{pid}/bible")
def put_bible(pid: str, bible: StoryBible) -> Project:
    p = writable(pid)
    p.bible = bible
    return store.save(p)


@app.put("/api/projects/{pid}/mix")
def put_mix(pid: str, mix: MixSettings) -> Project:
    p = writable(pid)
    p.mix = mix
    return store.save(p)


@app.put("/api/projects/{pid}/grade")
def put_grade(pid: str, grade: GradeSettings) -> Project:
    p = writable(pid)
    p.grade = grade
    return store.save(p)


@app.post("/api/projects/{pid}/characters/{cid}/reference")
async def upload_reference(pid: str, cid: str, request: Request, filename: str = "ref.png") -> Project:
    """Upload an identity reference image (raw body). Used for IP-Adapter / i2v keyframes."""
    p = writable(pid)
    c = p.bible.character(cid)
    if not c:
        raise HTTPException(404, "character not found")
    ext = Path(filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "png/jpg/webp only")
    data = await request.body()
    if not data or len(data) > 25_000_000:
        raise HTTPException(400, "empty or too large (25MB max)")
    out = store.media(pid, "refs") / f"{cid}_{len(c.reference_images) + 1}{ext}"
    out.write_bytes(data)
    c.reference_images.append(str(out.resolve()))
    return store.save(p)


# ------------------------------------------------------------------ screenplay editing
class NewScene(BaseModel):
    location_id: Optional[str] = None
    time_of_day: str = "DAY"
    beat: str = ""
    summary: str = ""
    mood: str = ""
    music_cue: str = ""
    action: list[str] = []
    dialogue: list[DialogueLine] = []
    after_scene_id: Optional[str] = None


@app.post("/api/projects/{pid}/scenes")
def add_scene(pid: str, body: NewScene) -> Project:
    """Write a new scene; the cinematographer designs its coverage automatically."""
    p = writable(pid)
    loc = p.bible.location(body.location_id or "") or (p.bible.locations[0] if p.bible.locations else None)
    sc = Scene(heading=f"{'INT' if (loc and loc.interior) else 'EXT'}. {(loc.name if loc else 'LOCATION').upper()} - "
                       f"{body.time_of_day.upper()}", location_id=loc.id if loc else None,
               time_of_day=body.time_of_day.upper(), beat=body.beat, summary=body.summary, mood=body.mood,
               music_cue=body.music_cue or f"{p.bible.style.music_style}, {body.mood}")
    idx = next((i + 1 for i, s in enumerate(p.scenes) if s.id == body.after_scene_id), len(p.scenes))
    sc.number = idx + 1
    design_coverage(sc, p.bible, SceneDraft(lines=body.dialogue, action=body.action))
    p.scenes.insert(idx, sc)
    renumber(p)
    return store.save(p)


@app.patch("/api/projects/{pid}/scenes/{sid}")
def patch_scene(pid: str, sid: str, patch: dict = Body(...)) -> Project:
    p = writable(pid)
    sc = p.find_scene(sid)
    if not sc:
        raise HTTPException(404, "scene not found")
    patch.pop("shots", None)
    p.scenes[p.scenes.index(sc)] = merge(sc, patch)
    return store.save(p)


@app.delete("/api/projects/{pid}/scenes/{sid}")
def delete_scene(pid: str, sid: str) -> Project:
    p = writable(pid)
    p.scenes = [s for s in p.scenes if s.id != sid]
    renumber(p)
    return store.save(p)


@app.put("/api/projects/{pid}/order")
def reorder_scenes(pid: str, scene_ids: list[str]) -> Project:
    p = writable(pid)
    by_id = {s.id: s for s in p.scenes}
    if set(scene_ids) != set(by_id):
        raise HTTPException(400, "must list every scene id exactly once")
    p.scenes = [by_id[i] for i in scene_ids]
    renumber(p)
    return store.save(p)


@app.put("/api/projects/{pid}/scenes/{sid}/order")
def reorder_shots(pid: str, sid: str, shot_ids: list[str]) -> Project:
    p = writable(pid)
    sc = p.find_scene(sid)
    if not sc:
        raise HTTPException(404, "scene not found")
    by_id = {s.id: s for s in sc.shots}
    if set(shot_ids) != set(by_id):
        raise HTTPException(400, "must list every shot id exactly once")
    sc.shots = [by_id[i] for i in shot_ids]
    renumber(p)
    return store.save(p)


@app.patch("/api/projects/{pid}/shots/{shid}")
def patch_shot(pid: str, shid: str, patch: dict = Body(...)) -> Project:
    p = writable(pid)
    sc, sh = p.find_shot(shid)
    if not sh:
        raise HTTPException(404, "shot not found")
    for k in ("id", "clip_path", "takes", "gen_key"):
        patch.pop(k, None)
    if "duration" in patch and not (0.5 <= float(patch["duration"]) <= 120):
        raise HTTPException(400, "duration must be 0.5-120s")
    sc.shots[sc.shots.index(sh)] = merge(sh, patch)
    return store.save(p)


@app.delete("/api/projects/{pid}/shots/{shid}")
def delete_shot(pid: str, shid: str) -> Project:
    p = writable(pid)
    sc, sh = p.find_shot(shid)
    if not sh:
        raise HTTPException(404, "shot not found")
    sc.shots.remove(sh)
    renumber(p)
    return store.save(p)


@app.post("/api/projects/{pid}/shots/{shid}/take/{n}")
def select_take(pid: str, shid: str, n: int) -> Project:
    """Swap in an earlier take of a shot (the current one goes back into the takes list)."""
    p = writable(pid)
    _, sh = p.find_shot(shid)
    if not sh or not (0 <= n < len(sh.takes)):
        raise HTTPException(404, "take not found")
    chosen = sh.takes.pop(n)
    if sh.clip_path:
        sh.takes.append(sh.clip_path)
    sh.clip_path, sh.status = chosen, Status.approved
    return store.save(p)


def renumber(p: Project) -> None:
    for i, sc in enumerate(p.scenes, 1):
        sc.number = i
        for j, sh in enumerate(sc.shots):
            sh.number = f"{i}{chr(65 + j) if j < 26 else 'Z' + str(j - 25)}"


# ------------------------------------------------------------------ intelligence
@app.get("/api/projects/{pid}/continuity")
def continuity(pid: str) -> list[dict]:
    return check_project(load(pid))


@app.get("/api/projects/{pid}/shots/{shid}/prompt")
def shot_prompt(pid: str, shid: str) -> dict:
    p = load(pid)
    sc, sh = p.find_shot(shid)
    if not sh:
        raise HTTPException(404, "shot not found")
    return compile_shot(p.bible, sc, sh).to_dict()


@app.get("/api/projects/{pid}/timeline")
def timeline(pid: str) -> dict:
    p = load(pid)
    entries, total = build_timeline(p.scenes)
    return {"duration": round(total, 3), "clips": [
        {"scene_id": e.scene.id, "scene": e.scene.number, "shot_id": e.shot.id, "number": e.shot.number,
         "start": round(e.start, 3), "duration": e.duration, "transition": e.transition.value, "overlap": e.tdur,
         "clip": e.shot.clip_path, "status": e.shot.status.value,
         "dialogue": [{"start": round(e.start + l.offset, 3), "duration": l.duration, "text": l.text,
                       "character_id": l.character_id} for l in e.shot.dialogue],
         "sounds": [{"start": round(e.start + s.offset, 3), "duration": s.duration, "description": s.description}
                    for s in e.shot.sounds]} for e in entries],
        "music": [{"scene_id": s.id, "path": s.music_path, "cue": s.music_cue} for s in p.scenes]}


@app.get("/api/projects/{pid}/screenplay", response_class=PlainTextResponse)
def screenplay(pid: str) -> str:
    """Industry-style plain-text screenplay export."""
    p = load(pid)
    out = [p.bible.title.upper().center(60), "", f"Logline: {p.bible.logline}", "", "FADE IN:", ""]
    for sc in p.scenes:
        out += [sc.heading, "", sc.summary, ""]
        for sh in sc.shots:
            if sh.action and not sh.dialogue:
                out += [sh.action, ""]
            for l in sh.dialogue:
                c = p.bible.character(l.character_id)
                out.append(" " * 22 + (c.name.upper() if c else "?"))
                if l.parenthetical:
                    out.append(" " * 16 + f"({l.parenthetical.strip('()')})")
                out += [" " * 10 + l.text, ""]
        out += [f"{sc.transition_out.value.upper().replace('_', ' ')} TO:".rjust(60), ""]
    out.append("FADE OUT.")
    return "\n".join(out)


@app.get("/api/projects/{pid}/dataset")
def dataset(pid: str) -> PlainTextResponse:
    """Approved shots as JSONL (prompt, conditioning, clip). Feed this to fine-tune your
    own video model / character LoRAs - the studio's data flywheel."""
    p = load(pid)
    rows = []
    for sc in p.scenes:
        for sh in sc.shots:
            if sh.status == Status.approved and sh.clip_path:
                req = compile_shot(p.bible, sc, sh).to_dict()
                rows.append(json.dumps({**req, "video": str(store.abspath(pid, sh.clip_path))}))
    return PlainTextResponse("\n".join(rows), media_type="application/jsonl")


# ------------------------------------------------------------------ production jobs
class RenderRequest(BaseModel):
    scene_id: Optional[str] = None
    force: bool = False


@app.post("/api/projects/{pid}/render")
def render(pid: str, body: RenderRequest = RenderRequest()) -> dict:
    p = writable(pid)
    job = runner.submit(pid, "render", lambda prog: studio.render(p, body.scene_id, prog, body.force).model_dump())
    return {"job_id": job.id}


@app.post("/api/projects/{pid}/shots/{shid}/generate")
def generate_shot(pid: str, shid: str) -> dict:
    p = writable(pid)
    sc, sh = p.find_shot(shid)
    if not sh:
        raise HTTPException(404, "shot not found")

    def work(prog):
        prog(0.1, f"Generating shot {sh.number}")
        studio.generate_shot(p, sc, sh, force=True)
        studio.generate_dialogue(p, sh)
        studio.generate_sfx(p, sh)
        store.save(p)
        return {"clip_path": sh.clip_path}

    return {"job_id": runner.submit(pid, "shot", work).id}


@app.get("/api/jobs")
def jobs(project_id: Optional[str] = None) -> list[dict]:
    return runner.list(project_id)


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    j = runner.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    from dataclasses import asdict
    return asdict(j)


# ------------------------------------------------------------------ media + UI
@app.get("/files/{pid}/{path:path}")
def files(pid: str, path: str) -> FileResponse:
    if not re.fullmatch(r"prj_[0-9a-f]{10}", pid):
        raise HTTPException(404)
    base = store.dir(pid).resolve()
    f = (base / path).resolve()
    if not f.is_relative_to(base / "media") or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
