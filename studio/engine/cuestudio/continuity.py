"""Script supervisor: automated continuity checks across the whole film."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .cinematography import speech_seconds
from .models import Project


@dataclass
class Issue:
    severity: str        # error | warning | info
    code: str
    message: str
    scene_id: str = ""
    shot_id: str = ""


def check_project(project: Project) -> list[dict]:
    b = project.bible
    issues: list[Issue] = []
    char_ids = {c.id for c in b.characters}
    loc_ids = {l.id for l in b.locations}
    prop_ids = {p.id for p in b.props}
    names = [c.name.lower() for c in b.characters]
    if len(names) != len(set(names)):
        issues.append(Issue("error", "duplicate_character", "Two characters share a name; identity will drift."))
    for c in b.characters:
        if not c.description:
            issues.append(Issue("warning", "missing_description",
                                f"{c.name} has no physical description; the model will invent a new face each shot."))
        if not c.reference_images and c.role in ("lead", "antagonist"):
            issues.append(Issue("info", "no_reference",
                                f"Add reference images (or train a LoRA) for {c.name} to lock identity."))
    last_wardrobe: dict[str, str] = {}
    for sc in project.scenes:
        if sc.location_id and sc.location_id not in loc_ids:
            issues.append(Issue("error", "unknown_location", f"Scene {sc.number} uses a deleted location.", sc.id))
        prev = None
        for sh in sc.shots:
            for cid in sh.character_ids:
                if cid not in char_ids:
                    issues.append(Issue("error", "unknown_character", f"Shot {sh.number} references a deleted character.",
                                        sc.id, sh.id))
            for pid in sh.prop_ids:
                if pid not in prop_ids:
                    issues.append(Issue("error", "unknown_prop", f"Shot {sh.number} references a deleted prop.", sc.id, sh.id))
            for line in sh.dialogue:
                if line.character_id not in sh.character_ids:
                    issues.append(Issue("warning", "offscreen_dialogue",
                                        f"Shot {sh.number}: speaker is not in frame (treated as V.O./O.S.).", sc.id, sh.id))
                need = line.offset + (line.duration or speech_seconds(line.text))
                if need > sh.duration + 0.05:
                    issues.append(Issue("warning", "dialogue_overrun",
                                        f"Shot {sh.number}: line needs {need:.1f}s but shot is {sh.duration:.1f}s.",
                                        sc.id, sh.id))
            for cid, costume in sh.wardrobe_overrides.items():
                if last_wardrobe.get(cid) not in (None, costume) and not sh.notes:
                    issues.append(Issue("info", "wardrobe_change",
                                        f"Shot {sh.number}: wardrobe change - confirm it is intentional.", sc.id, sh.id))
                last_wardrobe[cid] = costume
            if prev is not None:
                same_subject = set(prev.character_ids) == set(sh.character_ids) and sh.character_ids
                if same_subject and prev.size == sh.size and prev.angle == sh.angle and not sh.dialogue:
                    issues.append(Issue("warning", "jump_cut",
                                        f"Shot {sh.number}: same size/angle/subject as previous shot (jump cut).",
                                        sc.id, sh.id))
                for cid in set(prev.character_ids) & set(sh.character_ids):
                    if (len(prev.character_ids) == 1 and len(sh.character_ids) == 1 and
                            {prev.screen_direction, sh.screen_direction} == {"left_to_right", "right_to_left"}):
                        issues.append(Issue("warning", "crossed_line",
                                            f"Shot {sh.number}: screen direction flips for the same character "
                                            f"(180-degree rule).", sc.id, sh.id))
            if sh.duration < 1.0:
                issues.append(Issue("warning", "too_short", f"Shot {sh.number} is under one second.", sc.id, sh.id))
            prev = sh
    return [asdict(i) for i in issues]
