"""Director of Photography: turns a written scene into shot coverage.

Applies a deterministic, consistent camera grammar so every scene in the film
"feels" shot by the same crew:
  * establishing shot when we arrive at a location
  * a wide master that locks screen geography (180-degree rule)
  * shot / reverse-shot coverage for dialogue (OTS -> MCU -> CU as intensity rises)
  * reaction shots and prop inserts
  * a closing shot that hands off to the next scene's transition
Camera movement, lens and angle are chosen from the scene's beat and mood.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import (CameraAngle, CameraMove, DialogueLine, Scene, Shot, ShotSize, SoundCue, StoryBible,
                     Transition)

INTENSE = {"Catalyst", "Midpoint", "All Is Lost", "Finale", "Bad Guys Close In"}
INTIMATE = {"Dark Night of the Soul", "Debate", "Final Image", "Setup"}
KINETIC = {"Fun and Games", "Finale", "Break into Three"}

SCENE_TRANSITIONS = {
    "Opening Image": Transition.fade_black, "Catalyst": Transition.smash_cut, "Break into Two": Transition.dissolve,
    "Midpoint": Transition.cut, "All Is Lost": Transition.fade_black, "Dark Night of the Soul": Transition.dissolve,
    "Final Image": Transition.fade_black,
}


@dataclass
class SceneDraft:
    lines: list[DialogueLine] = field(default_factory=list)
    action: list[str] = field(default_factory=list)
    sounds: list[SoundCue] = field(default_factory=list)


def speech_seconds(text: str, rate: float = 1.0) -> float:
    words = max(1, len(text.split()))
    return round(words / (2.6 * rate) + 0.4, 2)


def _move_for(beat: str, size: ShotSize) -> CameraMove:
    if beat in KINETIC and size in (ShotSize.WS, ShotSize.MS, ShotSize.FS):
        return CameraMove.handheld if beat == "Finale" else CameraMove.steadicam
    if beat in INTIMATE and size in (ShotSize.MCU, ShotSize.CU):
        return CameraMove.dolly_in
    if beat in INTENSE and size == ShotSize.CU:
        return CameraMove.zoom_in
    return CameraMove.static


def _lens_for(size: ShotSize) -> int:
    return {ShotSize.EWS: 18, ShotSize.WS: 24, ShotSize.FS: 32, ShotSize.TWO: 35, ShotSize.MS: 40,
            ShotSize.OTS: 50, ShotSize.MCU: 65, ShotSize.CU: 85, ShotSize.ECU: 100, ShotSize.INSERT: 100,
            ShotSize.POV: 35}.get(size, 35)


def design_coverage(scene: Scene, bible: StoryBible, draft: SceneDraft) -> Scene:
    loc = bible.location(scene.location_id or "")
    cast = list(dict.fromkeys(l.character_id for l in draft.lines)) or [bible.characters[0].id]
    # 180-degree rule: first speaker always frame-left looking right, second frame-right looking left.
    side = {cid: ("left_to_right" if i % 2 == 0 else "right_to_left") for i, cid in enumerate(cast)}
    names = {c.id: c.name for c in bible.characters}
    beat = scene.beat
    shots: list[Shot] = []
    letter = iter("ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "".join(f"{a}{b}" for a in "AB" for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"))

    def add(**kw) -> Shot:
        size = kw.setdefault("size", ShotSize.MS)
        kw.setdefault("lens_mm", _lens_for(size))
        kw.setdefault("movement", _move_for(beat, size))
        sh = Shot(number=f"{scene.number}{next(letter)}", **kw)
        shots.append(sh)
        return sh

    action = list(draft.action)
    # 1. Establishing
    add(size=ShotSize.EWS, angle=CameraAngle.high, movement=CameraMove.crane_down if beat in KINETIC else CameraMove.pan_right,
        duration=4.0, action=f"Establish {loc.name if loc else 'the location'}, {scene.time_of_day.lower()}. "
                             f"{scene.mood} atmosphere.",
        mise_en_scene=(loc.set_dressing if loc else ""), lighting=(loc.lighting if loc else ""),
        transition_in=SCENE_TRANSITIONS.get(beat, Transition.cut),
        sounds=[SoundCue(description=scene.ambience or "room tone", kind="ambience", duration=4.0, volume=0.4)])
    # 2. Master
    blocking = "; ".join(f"{names.get(c, '?')} frame-{'left' if side[c] == 'left_to_right' else 'right'}"
                         for c in cast)
    add(size=ShotSize.TWO if len(cast) >= 2 else ShotSize.WS, angle=CameraAngle.eye, duration=4.0,
        action=action.pop(0) if action else scene.summary or "The characters take their positions.",
        blocking=blocking, character_ids=cast, screen_direction="neutral",
        mise_en_scene=(loc.set_dressing if loc else ""))
    # 3. Dialogue coverage
    prev_speaker = None
    for i, line in enumerate(draft.lines):
        speaker = line.character_id
        listener = next((c for c in cast if c != speaker), None)
        heat = beat in INTENSE or line.emotion.split(",")[0] in ("angry", "devastating", "shock", "fear", "sad")
        if i < 2 and listener:
            size = ShotSize.OTS
        elif heat or i >= 4:
            size = ShotSize.CU
        else:
            size = ShotSize.MCU
        angle = CameraAngle.low if (heat and speaker == bible.characters[-1].id) else CameraAngle.eye
        char = bible.character(speaker)
        rate = char.voice.rate if char else 1.0
        line.offset = 0.3
        dur = max(2.5, speech_seconds(line.text, rate) + 0.9)
        add(size=size, angle=angle, duration=round(dur, 2),
            action=(action.pop(0) if action else f"{names.get(speaker, '')} speaks, {line.emotion}."),
            blocking=(f"Over {names.get(listener, '')}'s shoulder onto {names.get(speaker, '')}" if size == ShotSize.OTS
                      else f"{names.get(speaker, '')} {line.parenthetical or 'delivers the line'}, eyeline "
                           f"{'screen-right' if side.get(speaker) == 'left_to_right' else 'screen-left'}"),
            character_ids=[speaker] + ([listener] if size == ShotSize.OTS and listener else []),
            dialogue=[line], screen_direction=side.get(speaker, "neutral"))
        # Reaction shot after an emotional beat
        if heat and listener and i % 2 == 1 and prev_speaker != listener:
            add(size=ShotSize.CU, duration=2.0, action=f"{names.get(listener, '')} reacts silently.",
                blocking=f"{names.get(listener, '')} holds the look", character_ids=[listener],
                screen_direction=side.get(listener, "neutral"), movement=CameraMove.static)
        prev_speaker = speaker
    # 4. Prop insert
    for p in bible.props:
        if p.owner_id in cast and (scene.number % 3 == 1 or beat in INTENSE):
            add(size=ShotSize.INSERT, duration=2.0, action=f"Close on the {p.name}: {p.description}.",
                prop_ids=[p.id], movement=CameraMove.dolly_in)
            break
    # Remaining action beats get their own shots
    for a in action:
        add(size=ShotSize.MS, duration=3.5, action=a, character_ids=cast[:2])
    # 5. Closing
    closing = ShotSize.WS if beat not in INTIMATE else ShotSize.MCU
    if shots[-1].size == closing or (closing == ShotSize.MCU and shots[-1].size == ShotSize.CU):
        closing = ShotSize.WS
    add(size=closing, duration=3.0,
        movement=CameraMove.dolly_out if beat not in KINETIC else CameraMove.crane_up,
        action=f"Hold on {names.get(cast[0], '')} as the moment settles. {scene.mood}.",
        character_ids=[cast[0]], screen_direction=side.get(cast[0], "neutral"))
    for s in draft.sounds:
        shots[min(1, len(shots) - 1)].sounds.append(s)
    for i, sh in enumerate(shots):
        sh.seed = (loc.seed if loc else 1) + scene.number * 1000 + i
    scene.shots = shots
    return scene
