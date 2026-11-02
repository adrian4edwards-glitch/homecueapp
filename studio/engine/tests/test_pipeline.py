"""End-to-end tests: prompt -> bible -> screenplay -> generation -> edit -> mix -> export."""
import os
import subprocess
import tempfile
import time

os.environ.setdefault("CUESTUDIO_DATA", tempfile.mkdtemp(prefix="cuestudio_test_"))

from fastapi.testclient import TestClient  # noqa: E402

from cuestudio.api import app, store  # noqa: E402
from cuestudio.cinematography import speech_seconds  # noqa: E402
from cuestudio.models import CreateRequest, Medium, Transition  # noqa: E402
from cuestudio.planner import Planner, allocate_beats  # noqa: E402
from cuestudio.studio import build_timeline  # noqa: E402

client = TestClient(app)
PROMPT = "A shy robot named Pip falls in love with a lighthouse keeper named Wren in a stormy fishing village"


def wait(job_id, timeout=600):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.5)
    raise TimeoutError


def test_beats_scale_to_feature_length():
    assert len(allocate_beats(3)) == 3
    feature = allocate_beats(120)
    assert len(feature) == 120 and feature[0] == "Opening Image" and feature[-1] == "Final Image"


def test_bible_is_consistent_and_named_from_prompt():
    p = Planner().create_project(CreateRequest(prompt=PROMPT, medium=Medium.animation_3d, target_minutes=1))
    names = [c.name for c in p.bible.characters]
    assert "Pip" in names and "Wren" in names
    assert "3D feature animation" in p.bible.style.look
    ids = {c.id for c in p.bible.characters}
    for sc in p.scenes:
        assert sc.shots[0].size.name == "EWS"                     # establishing shot first
        for sh in sc.shots:
            assert set(sh.character_ids) <= ids
            for line in sh.dialogue:                              # every line fits its shot
                assert line.offset + speech_seconds(line.text) <= sh.duration + 1e-6


def test_timeline_overlaps_transitions():
    p = Planner().create_project(CreateRequest(prompt=PROMPT, target_minutes=1))
    p.scenes[1].shots[0].transition_in = Transition.dissolve
    entries, total = build_timeline(p.scenes)
    assert abs(total - (p.duration - sum(e.tdur for e in entries))) < 1e-6
    assert any(e.tdur > 0 for e in entries)


def test_api_full_production():
    r = client.post("/api/projects", json={"prompt": PROMPT, "medium": "cartoon_2d", "target_minutes": 0.5,
                                           "aspect_ratio": "16:9"})
    assert r.status_code == 200, r.text
    p = r.json()
    pid = p["id"]
    # edit the bible: wardrobe change must flow into compiled prompts
    bible = p["bible"]
    bible["characters"][0]["wardrobe"] = "bright yellow raincoat"
    assert client.put(f"/api/projects/{pid}/bible", json=bible).status_code == 200
    sc = p["scenes"][0]
    shot = next(s for s in sc["shots"] if s["character_ids"])
    cid = shot["character_ids"][0]
    if cid == bible["characters"][0]["id"]:
        assert "yellow raincoat" in client.get(f"/api/projects/{pid}/shots/{shot['id']}/prompt").json()["prompt"]
    # edit a shot + add a dissolve so the xfade path is exercised
    assert client.patch(f"/api/projects/{pid}/shots/{sc['shots'][1]['id']}",
                        json={"duration": 3.0, "transition_in": "dissolve"}).status_code == 200
    assert client.get(f"/api/projects/{pid}/continuity").status_code == 200
    assert "FADE IN:" in client.get(f"/api/projects/{pid}/screenplay").text
    job = client.post(f"/api/projects/{pid}/render", json={}).json()
    assert client.patch(f"/api/projects/{pid}/shots/{shot['id']}", json={"duration": 2}).status_code == 409  # locked
    j = wait(job["job_id"])
    assert j["status"] == "done", j["error"]
    res = j["result"]
    tl = client.get(f"/api/projects/{pid}/timeline").json()
    assert abs(res["duration"] - tl["duration"]) < 0.25
    video = client.get(f"/files/{pid}/{res['video_path']}")
    assert video.status_code == 200 and len(video.content) > 10_000
    assert "-->" in client.get(f"/files/{pid}/{res['subtitles_path']}").text
    assert "FCM: NON-DROP FRAME" in client.get(f"/files/{pid}/{res['edl_path']}").text
    # final master has picture + audio
    path = str(store.dir(pid) / res["video_path"])
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout.split()
    assert streams == ["video", "audio"]
    # regenerate one shot -> new take, old one kept
    j2 = wait(client.post(f"/api/projects/{pid}/shots/{shot['id']}/generate").json()["job_id"])
    assert j2["status"] == "done", j2["error"]
    sh = client.get(f"/api/projects/{pid}").json()["scenes"][0]["shots"]
    assert any(s["takes"] for s in sh)
    # path traversal is blocked
    assert client.get(f"/files/{pid}/../project.json").status_code == 404
