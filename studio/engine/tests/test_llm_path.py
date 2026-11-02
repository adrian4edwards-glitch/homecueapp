"""The writers' room path with a (stubbed) self-hosted LLM, plus graceful fallback."""
from cuestudio.llm import extract_json
from cuestudio.models import CreateRequest
from cuestudio.planner import Planner

BIBLE = {"title": "Signal Fire", "logline": "A keeper hears her daughter on the radio.", "theme": "grief",
         "synopsis": "...", "outline": ["Act 1", "Act 2", "Act 3"],
         "characters": [{"name": "Ruth", "role": "lead", "description": "60s, silver crop", "wardrobe": "flight suit",
                         "voice": {"gender": "female", "accent": "Texan"}},
                        {"name": "Kira", "role": "supporting", "description": "20s", "wardrobe": "hoodie"}],
         "locations": [{"name": "Station Ring", "interior": True, "description": "curved corridor"}],
         "props": [{"name": "Radio", "description": "cracked handset", "owner": "Ruth"}]}


class FakeLLM:
    available = True

    def chat_json(self, system, user, temperature=0.7):
        if "showrunner" in system.lower():
            return BIBLE
        n = int(user.split("Write ")[1].split(" ")[0])
        return {"scenes": [{"beat": "x", "location": "Station Ring", "time_of_day": "NIGHT", "summary": f"scene {i}",
                 "mood": "tense", "music_cue": "drone", "ambience": "hum", "action": ["Ruth grabs the radio."],
                 "dialogue": [{"character": "Ruth", "text": "Kira? Is that you?", "emotion": "shock"},
                              {"character": "Kira", "text": "Mom. Don't hang up.", "emotion": "fear"},
                              {"character": "Nobody", "text": "dropped: unknown speaker"}],
                 "sounds": ["radio static"]} for i in range(n)]}


class BrokenLLM:
    available = True

    def chat_json(self, *a, **k):
        raise ConnectionError("model server down")


def test_llm_bible_and_screenplay():
    p = Planner(FakeLLM()).create_project(CreateRequest(prompt="x", target_minutes=1))
    assert p.bible.title == "Signal Fire"
    assert [c.name for c in p.bible.characters][:2] == ["Ruth", "Kira"] and len(p.bible.characters) >= 3
    assert p.bible.characters[0].voice.accent == "Texan"
    assert p.bible.props[0].owner_id == p.bible.characters[0].id
    sc = p.scenes[0]
    assert sc.heading == "INT. STATION RING - NIGHT"
    lines = [l.text for sh in sc.shots for l in sh.dialogue]
    assert lines == ["Kira? Is that you?", "Mom. Don't hang up."]
    assert any(s.description == "radio static" for sh in sc.shots for s in sh.sounds)


def test_llm_failure_falls_back_to_builtin_writer():
    p = Planner(BrokenLLM()).create_project(CreateRequest(prompt="A heist in a casino", target_minutes=1))
    assert p.scenes and all(sc.shots for sc in p.scenes)


def test_extract_json_handles_fences_and_prose():
    assert extract_json('Sure!\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert extract_json('here: [{"x": 1}] thanks') == [{"x": 1}]
