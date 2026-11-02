"""Compile a shot into a generation request.

The compiled request carries everything a video model needs to stay
consistent: the same canonical character descriptions and wardrobe in every
shot, identity reference images / LoRAs, a location seed, the global look,
palette and lens package, and explicit camera language.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .models import Scene, Shot, StoryBible


@dataclass
class GenerationRequest:
    prompt: str
    negative_prompt: str
    width: int
    height: int
    fps: int
    duration: float
    seed: int
    reference_images: list[str] = field(default_factory=list)
    loras: list[str] = field(default_factory=list)
    camera: dict = field(default_factory=dict)
    shot_id: str = ""
    scene_heading: str = ""
    palette: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    dialogue: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def compile_shot(bible: StoryBible, scene: Scene, shot: Shot) -> GenerationRequest:
    st = bible.style
    loc = bible.location(scene.location_id or "")
    parts: list[str] = [
        f"{shot.size.value}, {shot.angle.value}, {shot.movement.value}, {shot.lens_mm}mm lens",
        st.look,
    ]
    if loc:
        parts.append(f"{'interior' if loc.interior else 'exterior'} {loc.name}, {scene.time_of_day.lower()}: "
                     f"{loc.description}")
    refs: list[str] = []
    loras: list[str] = []
    names: list[str] = []
    for cid in shot.character_ids:
        c = bible.character(cid)
        if not c:
            continue
        names.append(c.name)
        wardrobe = shot.wardrobe_overrides.get(cid, c.wardrobe)
        desc = f"{c.name}: {c.description}" + (f", wearing {wardrobe}" if wardrobe else "")
        if c.mannerisms:
            desc += f", {c.mannerisms}"
        parts.append(desc)
        refs += c.reference_images[:2]
        if c.lora:
            loras.append(c.lora)
    if shot.action:
        parts.append(f"Action: {shot.action}")
    if shot.blocking:
        parts.append(f"Blocking: {shot.blocking}")
    for line in shot.dialogue:
        c = bible.character(line.character_id)
        if c:
            parts.append(f"{c.name} speaking{' ' + line.parenthetical if line.parenthetical else ''}, "
                         f"{line.emotion} expression, natural lip movement")
    for pid in shot.prop_ids:
        p = bible.prop(pid)
        if p:
            parts.append(f"{p.name}: {p.description}")
            refs += p.reference_images[:1]
    mise = shot.mise_en_scene or (loc.set_dressing if loc else "")
    if mise:
        parts.append(f"Set: {mise}")
    parts.append(f"Lighting: {shot.lighting or (loc.lighting if loc else '') or st.lighting_style}")
    parts.append(f"Mood: {scene.mood or st.tone}")
    parts.append(f"Color palette {', '.join(st.palette)}; {st.film_stock}; {st.lens_package}")
    if loc:
        refs += loc.reference_images[:1]
    prompt = ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip()) + "."
    return GenerationRequest(
        prompt=prompt, negative_prompt=st.negative_prompt, width=st.width, height=st.height, fps=st.fps,
        duration=shot.duration, seed=shot.seed or 0, reference_images=refs, loras=loras,
        camera={"size": shot.size.value, "angle": shot.angle.value, "movement": shot.movement.value,
                "lens_mm": shot.lens_mm, "screen_direction": shot.screen_direction},
        shot_id=shot.id, scene_heading=scene.heading, palette=st.palette, characters=names,
        dialogue=[l.text for l in shot.dialogue],
    )
