"""Writers' room: prompt -> Story Bible -> Screenplay (scenes + dialogue).

Uses your self-hosted LLM when CUESTUDIO_LLM_URL is set. Without one, a
built-in structural writer produces a complete, valid (if generic) script so
the whole pipeline always runs. Either way the result is handed to the
Cinematographer (cinematography.py) which designs shot coverage with a
consistent camera grammar.
"""
from __future__ import annotations

import hashlib
import logging
import random
import re
from typing import Any, Optional

from .cinematography import SceneDraft, design_coverage
from .llm import LocalLLM
from .models import (Character, CreateRequest, DialogueLine, Location, Project, Prop, Scene,
                     SoundCue, StoryBible, VoiceProfile)
from .styles import build_style, detect_genre

log = logging.getLogger(__name__)

# Beat sheet: (name, share of runtime, dramatic purpose)
BEATS: list[tuple[str, float, str]] = [
    ("Opening Image", 0.02, "establish the world and the hero's flaw"),
    ("Setup", 0.08, "show the hero's ordinary life and what is missing"),
    ("Catalyst", 0.04, "an event upends everything"),
    ("Debate", 0.08, "the hero resists the call"),
    ("Break into Two", 0.04, "the hero commits to the journey"),
    ("Fun and Games", 0.16, "the promise of the premise"),
    ("Midpoint", 0.06, "a false victory or false defeat raises the stakes"),
    ("Bad Guys Close In", 0.14, "opposition tightens; the team fractures"),
    ("All Is Lost", 0.05, "the lowest point"),
    ("Dark Night of the Soul", 0.07, "the hero confronts the flaw"),
    ("Break into Three", 0.04, "a new plan from what was learned"),
    ("Finale", 0.18, "the climactic confrontation"),
    ("Final Image", 0.04, "mirror of the opening: show the change"),
]

STOPWORDS = {
    "The", "A", "An", "In", "On", "At", "When", "After", "Before", "With", "And", "But", "Or", "For",
    "Make", "Create", "Generate", "Film", "Movie", "Story", "Write", "About", "Where", "Who", "Their",
    "His", "Her", "They", "She", "He", "It", "This", "That", "Pixar", "Hollywood", "Disney", "AI",
    "One", "Two", "Three", "Then", "Once", "Upon", "Time", "City", "New", "From", "Into", "Our", "My",
}
FALLBACK_NAMES = ["Maya", "Elias", "Nora", "Theo", "Iris", "Marcus", "Lena", "Jonah", "Ava", "Cyrus"]
LOOKS = [
    ("early 30s, warm brown skin, short natural curls, athletic build, determined dark eyes",
     "olive field jacket over a grey henley, dark jeans, worn leather boots"),
    ("late 40s, pale weathered skin, salt-and-pepper beard, tall and lean, piercing blue eyes",
     "charcoal three-piece suit, black overcoat, silver signet ring"),
    ("mid 20s, East Asian, shoulder-length black hair with a blue streak, slim, quick expressive eyes",
     "oversized mustard hoodie, cargo pants, white high-top sneakers"),
    ("60s, South Asian, silver hair in a bun, kind lined face, round glasses",
     "cream cardigan, burgundy scarf, long navy skirt"),
    ("early 20s, freckled fair skin, messy red hair, wiry build, gap-toothed grin",
     "denim jacket covered in patches, striped t-shirt, red sneakers"),
]
GENRE_LOCATIONS = {
    "sci-fi": [("Starship Bridge", True), ("Research Lab", True), ("Alien Desert", False)],
    "horror": [("Old Farmhouse", True), ("Fog-covered Woods", False), ("Cellar", True)],
    "thriller": [("Rain-soaked Alley", False), ("Police Precinct", True), ("Penthouse Office", True)],
    "action": [("Abandoned Warehouse", True), ("Rooftop", False), ("Highway Overpass", False)],
    "fantasy": [("Ancient Forest", False), ("Castle Throne Room", True), ("Mountain Pass", False)],
    "romance": [("Corner Cafe", True), ("Riverside Promenade", False), ("Small Apartment", True)],
    "comedy": [("Chaotic Kitchen", True), ("Suburban Street", False), ("Office Break Room", True)],
    "family": [("Cozy Bedroom", True), ("Backyard Treehouse", False), ("Town Square", False)],
}
DEFAULT_LOCATIONS = [("Apartment", True), ("City Street", False), ("Rooftop", False)]

# Dialogue templates per beat. Roles: L=lead, A=ally, X=antagonist.
LINES: dict[str, list[tuple[str, str]]] = {
    "Opening Image": [("L", "Same as every morning. Nothing ever changes here.")],
    "Setup": [("A", "You keep saying you want more, {L}."), ("L", "Wanting isn't the same as doing.")],
    "Catalyst": [("A", "Did you see this? It's about {premise}."), ("L", "That's impossible.")],
    "Debate": [("L", "I can't. Not me. Not now."), ("A", "If not you, then who?")],
    "Break into Two": [("L", "Fine. We do this together, or not at all."), ("A", "Together.")],
    "Fun and Games": [("A", "I can't believe this is actually working!"), ("L", "Don't jinx it.")],
    "Midpoint": [("X", "You think you've won something, {L}?"), ("L", "I think you're scared.")],
    "Bad Guys Close In": [("A", "You didn't tell me the truth."), ("L", "I was trying to protect you.")],
    "All Is Lost": [("L", "It's over. I've lost everything.")],
    "Dark Night of the Soul": [("A", "You were never doing it for them. You were doing it for you."),
                               ("L", "Then maybe it's time I did it for the right reason.")],
    "Break into Three": [("L", "I know what we have to do."), ("A", "Then let's finish it.")],
    "Finale": [("X", "You should have walked away."), ("L", "I almost did. That's the difference between us.")],
    "Final Image": [("L", "Same place. Different me.")],
}
MOODS = {
    "Opening Image": "quiet, contemplative", "Setup": "grounded, warm", "Catalyst": "shock, disruption",
    "Debate": "hesitant, conflicted", "Break into Two": "resolve", "Fun and Games": "exhilarating, playful",
    "Midpoint": "triumphant yet uneasy", "Bad Guys Close In": "tense, claustrophobic",
    "All Is Lost": "devastating", "Dark Night of the Soul": "somber, introspective",
    "Break into Three": "hopeful determination", "Finale": "epic, climactic", "Final Image": "serene, earned",
}


def stable_seed(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


class Planner:
    def __init__(self, llm: Optional[LocalLLM] = None):
        self.llm = llm or LocalLLM()

    # ------------------------------------------------------------------ public
    def create_project(self, req: CreateRequest) -> Project:
        genre = (req.genre or detect_genre(req.prompt)).lower()
        bible = self.build_bible(req, genre)
        drafts = self.write_screenplay(bible, req.prompt, req.target_minutes)
        scenes = [design_coverage(sc, bible, draft) for sc, draft in drafts]
        actual, target = sum(sc.duration for sc in scenes), req.target_minutes * 60
        if not self.llm.available and scenes and actual < 0.9 * target:
            # Built-in writer: calibrate the scene count to the coverage it actually produces.
            drafts = self.write_screenplay(bible, req.prompt, req.target_minutes, scene_seconds=actual / len(scenes))
            scenes = [design_coverage(sc, bible, draft) for sc, draft in drafts]
        return Project(prompt=req.prompt, bible=bible, scenes=scenes)

    def build_bible(self, req: CreateRequest, genre: str) -> StoryBible:
        style = build_style(req.medium, genre, req.aspect_ratio)
        bible: Optional[StoryBible] = None
        if self.llm.available:
            try:
                bible = self._llm_bible(req, genre)
            except Exception as e:  # never let a flaky model kill the pipeline
                log.warning("LLM bible failed, using built-in writer: %s", e)
        if bible is None:
            bible = self._heuristic_bible(req, genre)
        bible.genre = genre
        bible.style = style
        if req.title:
            bible.title = req.title
        palette_cycle = ["#f59e0b", "#38bdf8", "#f43f5e", "#a3e635", "#c084fc", "#2dd4bf"]
        for i, c in enumerate(bible.characters):
            c.identity_seed = c.identity_seed or stable_seed(bible.title, c.name)
            c.color = palette_cycle[i % len(palette_cycle)]
            if c.voice.pitch == 1.0:
                c.voice.pitch = {"female": 1.25, "male": 0.85}.get(c.voice.gender, 1.0) * (1 + (i % 3) * 0.05)
        for l in bible.locations:
            l.seed = l.seed or stable_seed(bible.title, l.name)
        return bible

    def write_screenplay(self, bible: StoryBible, premise: str, minutes: float,
                         scene_seconds: float = 45.0) -> list[tuple[Scene, SceneDraft]]:
        n_scenes = min(600, max(3, round(minutes * 60 / max(5.0, scene_seconds))))
        plan = allocate_beats(n_scenes)
        scenes: Optional[list[tuple[Scene, SceneDraft]]] = None
        if self.llm.available:
            try:
                scenes = self._llm_screenplay(bible, premise, plan)
            except Exception as e:
                log.warning("LLM screenplay failed, using built-in writer: %s", e)
        if not scenes:
            scenes = self._heuristic_screenplay(bible, premise, plan)
        for i, (sc, _) in enumerate(scenes, 1):
            sc.number = i
        return scenes

    # ------------------------------------------------------------------ built-in writer
    def _heuristic_bible(self, req: CreateRequest, genre: str) -> StoryBible:
        chars: list[Character] = []
        for i, seed in enumerate(req.characters):
            name, _, desc = seed.partition(":")
            chars.append(Character(name=name.strip(), description=desc.strip() or LOOKS[i % len(LOOKS)][0],
                                   wardrobe=LOOKS[i % len(LOOKS)][1]))
        found = [n for n in dict.fromkeys(re.findall(r"\b[A-Z][a-z]{2,}\b", req.prompt)) if n not in STOPWORDS]
        for n in found:
            if len(chars) >= 3:
                break
            if all(c.name != n for c in chars):
                i = len(chars)
                chars.append(Character(name=n, description=LOOKS[i % len(LOOKS)][0], wardrobe=LOOKS[i % len(LOOKS)][1]))
        used = {c.name for c in chars}
        pool = [n for n in FALLBACK_NAMES if n not in used]
        while len(chars) < 3:
            i = len(chars)
            chars.append(Character(name=pool.pop(stable_seed(req.prompt, i) % len(pool)),
                                   description=LOOKS[i % len(LOOKS)][0], wardrobe=LOOKS[i % len(LOOKS)][1]))
        roles = ["lead", "supporting", "antagonist"]
        for i, c in enumerate(chars):
            c.role = roles[i] if i < 3 else "supporting"
            c.voice = VoiceProfile(voice_id=f"voice_{i}", gender=["female", "male", "male", "female"][i % 4],
                                   timbre=["warm", "gravelly", "bright", "soft"][i % 4])
        lead, ally, antag = chars[0], chars[1], chars[2]
        lead.personality, lead.motivation = "guarded, stubborn, secretly hopeful", "prove they matter"
        lead.arc = "from isolation and fear to trust and courage"
        ally.personality, ally.motivation = "loyal, funny, perceptive", "keep the lead from self-destructing"
        ally.arc = "from sidekick to equal partner"
        antag.personality, antag.motivation = "controlled, charismatic, ruthless", "keep the status quo at any cost"
        antag.arc = "from untouchable to exposed"

        setting = extract_setting(req.prompt)
        locs = list(GENRE_LOCATIONS.get(genre, DEFAULT_LOCATIONS))
        if setting:
            locs.insert(0, (setting.title(), not any(w in setting for w in OUTDOOR)))
        locations = [Location(name=n, interior=interior,
                              description=f"{n.lower()} rendered with consistent architecture and layout",
                              set_dressing="recurring set dressing locked for continuity",
                              lighting="consistent practicals and motivated key light")
                     for n, interior in locs[:4]]
        props = [Prop(name="Keepsake", description="small, worn object tied to the lead's past", owner_id=lead.id)]
        title = req.title or derive_title(req.prompt, [c.name for c in chars])
        return StoryBible(
            title=title, logline=req.prompt.strip()[:300], theme="what we risk when we finally choose to care",
            synopsis=req.prompt.strip(), outline=[f"{b}: {p}" for b, _, p in BEATS],
            characters=chars, locations=locations, props=props,
        )

    def _heuristic_screenplay(self, bible: StoryBible, premise: str, plan: list[str]) -> list[tuple[Scene, SceneDraft]]:
        roles = {"L": bible.characters[0], "A": bible.characters[1], "X": bible.characters[2]}
        names = {k: v.name for k, v in roles.items()}
        short = premise.strip().rstrip(".")
        short = short[0].lower() + short[1:] if short else "this"
        if len(short) > 80:
            short = short[:80].rsplit(" ", 1)[0] + "..."
        scenes: list[tuple[Scene, SceneDraft]] = []
        rng = random.Random(stable_seed(bible.title))
        for i, beat in enumerate(plan):
            loc = bible.locations[(i * 7 + rng.randint(0, 2)) % len(bible.locations)] if i else bible.locations[0]
            tod = rng.choice(["DAY", "DAY", "NIGHT", "DUSK", "DAWN"]) if i else "DAWN"
            lines = []
            for role, tpl in LINES[beat]:
                lines.append(DialogueLine(character_id=roles[role].id, text=tpl.format(premise=short, **names),
                                          emotion=MOODS[beat].split(",")[0]))
            sc = Scene(
                heading=f"{'INT' if loc.interior else 'EXT'}. {loc.name.upper()} - {tod}",
                location_id=loc.id, time_of_day=tod, beat=beat,
                summary=f"{beat}: {dict((b, p) for b, _, p in BEATS)[beat]}.",
                mood=MOODS[beat], color_mood=MOODS[beat], music_cue=f"{bible.style.music_style}, {MOODS[beat]}",
                ambience=f"{loc.name.lower()} room tone" if loc.interior else f"{loc.name.lower()} exterior ambience",
            )
            scenes.append((sc, SceneDraft(lines=lines)))
        return scenes

    # ------------------------------------------------------------------ LLM writer
    def _llm_bible(self, req: CreateRequest, genre: str) -> StoryBible:
        system = ("You are a showrunner and development executive. Build a production story bible. "
                  "Physical character descriptions must be concrete and visual (age, ethnicity, build, face, hair) "
                  "so an image model can reproduce the same person in every shot.")
        user = f"""Premise: {req.prompt}
Genre: {genre}. Medium: {req.medium.value}. Runtime: {req.target_minutes} minutes.
Seed characters (optional): {req.characters}
Return JSON: {{"title":str,"logline":str,"theme":str,"synopsis":str,"outline":[str],
"characters":[{{"name":str,"role":"lead|antagonist|supporting","description":str,"wardrobe":str,
"personality":str,"motivation":str,"arc":str,"mannerisms":str,
"voice":{{"gender":"female|male|neutral","age":str,"accent":str,"timbre":str}}}}],
"locations":[{{"name":str,"interior":bool,"description":str,"set_dressing":str,"lighting":str}}],
"props":[{{"name":str,"description":str,"owner":str}}]}}
Use 3-8 characters (first is the lead), 3-10 locations, 1-8 props."""
        data = self.llm.chat_json(system, user)
        chars = [Character(**{k: v for k, v in c.items() if k in Character.model_fields and k != "voice"},
                           voice=VoiceProfile(voice_id=f"voice_{i}", **{k: v for k, v in (c.get("voice") or {}).items()
                                                                        if k in VoiceProfile.model_fields}))
                 for i, c in enumerate(data["characters"])]
        if len(chars) < 2:
            raise ValueError("model returned too few characters")
        while len(chars) < 3:
            chars.append(Character(name=FALLBACK_NAMES[len(chars)], role="supporting"))
        locs = [Location(**{k: v for k, v in l.items() if k in Location.model_fields}) for l in data["locations"]]
        by_name = {c.name.lower(): c.id for c in chars}
        props = [Prop(name=p["name"], description=p.get("description", ""),
                      owner_id=by_name.get(str(p.get("owner", "")).lower())) for p in data.get("props", [])]
        return StoryBible(title=data.get("title", "Untitled"), logline=data.get("logline", ""),
                          theme=data.get("theme", ""), synopsis=data.get("synopsis", ""),
                          outline=data.get("outline", []), characters=chars, locations=locs or
                          [Location(name=n, interior=i) for n, i in DEFAULT_LOCATIONS], props=props)

    def _llm_screenplay(self, bible: StoryBible, premise: str, plan: list[str]) -> list[tuple[Scene, SceneDraft]]:
        char_doc = "\n".join(f"- {c.name} ({c.role}): {c.personality}; wants {c.motivation}; arc: {c.arc}"
                             for c in bible.characters)
        loc_names = [l.name for l in bible.locations]
        system = ("You are an award-winning screenwriter. Write lean, visual scenes with subtext-rich dialogue. "
                  "Stay strictly consistent with the story bible.")
        scenes: list[tuple[Scene, SceneDraft]] = []
        chunk = 8
        for start in range(0, len(plan), chunk):
            beats = plan[start:start + chunk]
            prev = " | ".join(s.summary for s, _ in scenes[-3:])
            user = f"""Title: {bible.title}. Logline: {bible.logline}. Theme: {bible.theme}. Tone: {bible.style.tone}.
Characters:\n{char_doc}\nLocations (use exactly these names): {loc_names}
Previously: {prev or 'This is the start of the film.'}
Write {len(beats)} consecutive scenes, one per beat, in order: {beats}.
Return JSON list: [{{"beat":str,"location":str,"time_of_day":"DAY|NIGHT|DUSK|DAWN","summary":str,"mood":str,
"music_cue":str,"ambience":str,"action":[str],"dialogue":[{{"character":str,"text":str,"parenthetical":str,"emotion":str}}],
"sounds":[str]}}]. 2-8 dialogue lines per scene; character names must match the list."""
            data = self.llm.chat_json(system, user)
            if isinstance(data, dict):  # models often wrap the list: {"scenes": [...]}
                data = next((v for v in data.values() if isinstance(v, list)), [])
            for j, s in enumerate(data[: len(beats)]):
                scenes.append(self._scene_from_llm(bible, s, beats[j]))
        if len(scenes) < len(plan) // 2:
            raise ValueError("model returned too few scenes")
        return scenes

    def _scene_from_llm(self, bible: StoryBible, s: dict, beat: str) -> tuple[Scene, SceneDraft]:
        by_name = {c.name.lower(): c for c in bible.characters}
        loc = next((l for l in bible.locations if l.name.lower() == str(s.get("location", "")).lower()),
                   bible.locations[0])
        tod = str(s.get("time_of_day", "DAY")).upper()
        lines = []
        for d in s.get("dialogue", []):
            c = by_name.get(str(d.get("character", "")).lower())
            if c and d.get("text"):
                lines.append(DialogueLine(character_id=c.id, text=d["text"], parenthetical=d.get("parenthetical", ""),
                                          emotion=d.get("emotion", "neutral")))
        sc = Scene(heading=f"{'INT' if loc.interior else 'EXT'}. {loc.name.upper()} - {tod}", location_id=loc.id,
                   time_of_day=tod, beat=s.get("beat", beat), summary=s.get("summary", ""), mood=s.get("mood", ""),
                   color_mood=s.get("mood", ""), music_cue=s.get("music_cue", ""), ambience=s.get("ambience", ""))
        return sc, SceneDraft(lines=lines, action=[a for a in s.get("action", []) if isinstance(a, str)],
                              sounds=[SoundCue(description=x) for x in s.get("sounds", []) if isinstance(x, str)])


def allocate_beats(n_scenes: int) -> list[str]:
    """Distribute n scenes over the beat sheet proportional to each beat's share."""
    if n_scenes < len(BEATS):
        idx = sorted({round(i * (len(BEATS) - 1) / max(1, n_scenes - 1)) for i in range(n_scenes)})
        while len(idx) < n_scenes:
            idx = sorted(set(idx) | {next(i for i in range(len(BEATS)) if i not in idx)})
        return [BEATS[i][0] for i in idx]
    counts = [max(1, round(share * n_scenes)) for _, share, _ in BEATS]
    while sum(counts) > n_scenes:
        counts[counts.index(max(counts))] -= 1
    while sum(counts) < n_scenes:
        counts[5] += 1  # extra scenes go to "Fun and Games"
    return [b for (b, _, _), c in zip(BEATS, counts) for _ in range(c)]


FUNCTION_WORDS = {"who", "that", "which", "named", "called", "to", "in", "on", "at", "of", "from", "and", "or", "but",
                  "with", "for", "where", "when", "while", "because", "must", "is", "are", "was", "has", "into", "after"}
OUTDOOR = ("city", "street", "village", "forest", "desert", "beach", "ocean", "sea", "mountain", "island", "field",
           "planet", "jungle", "town", "park", "road", "highway", "valley", "river", "lake", "sky")


def _phrases(text: str) -> list[tuple[int, list[str]]]:
    """Noun phrases introduced by an article: 'a neon city to save...' -> ['neon', 'city']."""
    out = []
    words = re.findall(r"[A-Za-z'-]+|[.,;!?]", text)
    for i, w in enumerate(words):
        if w.lower() in ("a", "an", "the"):
            phrase = []
            for nxt in words[i + 1:i + 5]:
                if nxt in ".,;!?" or nxt.lower() in FUNCTION_WORDS:
                    break
                phrase.append(nxt)
            if phrase:
                out.append((i, phrase))
    return out


def extract_setting(prompt: str) -> str:
    words = re.findall(r"[A-Za-z'-]+|[.,;!?]", prompt)
    for i, phrase in _phrases(prompt):
        if i and words[i - 1].lower() in ("in", "inside", "on", "at", "aboard", "across", "within"):
            return " ".join(phrase[:3]).lower()
    return ""


def derive_title(prompt: str, names: list[str]) -> str:
    """'A retired astronaut discovers a signal from ...' -> 'The Signal'."""
    heads = [ph[-1] for _, ph in _phrases(prompt) if ph[-1].capitalize() not in names and len(ph[-1]) > 2]
    if len(heads) >= 2:
        return f"The {heads[1].capitalize()}"
    if heads:
        return f"The {heads[0].capitalize()}"
    return f"{names[0]}'s Story" if names else "Untitled"
