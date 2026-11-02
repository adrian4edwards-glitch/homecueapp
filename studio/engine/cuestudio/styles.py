"""Look presets per medium and genre."""
from __future__ import annotations

from .models import Medium, StyleGuide

MEDIUM_LOOKS: dict[Medium, dict] = {
    Medium.live_action: dict(
        look="photorealistic cinematic Hollywood feature film, real human actors, natural skin texture",
        lens_package="anamorphic prime lenses, shallow depth of field",
        film_stock="35mm film grain, Kodak Vision3 500T",
        lighting_style="motivated naturalistic lighting, soft key light, deep controlled shadows",
    ),
    Medium.animation_3d: dict(
        look="high-end 3D feature animation, stylised appealing characters, subsurface scattering, "
             "expressive faces, global illumination",
        lens_package="virtual camera, cinematic depth of field",
        film_stock="clean render, no grain",
        lighting_style="soft bounce light, warm rim lights, storybook atmosphere",
    ),
    Medium.cartoon_2d: dict(
        look="hand-drawn 2D cartoon animation, clean line art, flat cel shading, squash and stretch",
        lens_package="flat 2D staging, layered parallax backgrounds",
        film_stock="clean",
        lighting_style="graphic flat lighting with simple shadow shapes",
    ),
    Medium.anime: dict(
        look="cinematic anime film, painted backgrounds, detailed line art, dramatic sky",
        lens_package="anime layout, parallax, lens flares",
        film_stock="clean",
        lighting_style="high contrast cel lighting, glowing highlights",
    ),
    Medium.stop_motion: dict(
        look="stop-motion animation, handcrafted puppets, miniature sets, tactile materials",
        lens_package="macro lens, tilt-shift miniature depth",
        film_stock="subtle frame jitter",
        lighting_style="practical miniature lighting",
    ),
    Medium.motion_graphics: dict(
        look="premium motion graphics, kinetic typography, clean 3D shapes, smooth easing",
        lens_package="virtual camera, orthographic and perspective moves",
        film_stock="clean",
        lighting_style="studio gradient lighting",
    ),
}

GENRES: dict[str, dict] = {
    "thriller": dict(palette=["#0b1320", "#1c3d5a", "#c0392b", "#d9d9d9"], tone="tense, suspenseful",
                     grade="cool", music_style="pulsing synth and low strings"),
    "horror": dict(palette=["#050505", "#2b0f0f", "#5c1a1a", "#9ca3af"], tone="dread, unsettling",
                   grade="noir", music_style="dissonant drones, sparse piano"),
    "sci-fi": dict(palette=["#020617", "#0e7490", "#22d3ee", "#f472b6"], tone="awe, wonder, cold precision",
                   grade="teal_orange", music_style="epic synth-orchestral hybrid"),
    "comedy": dict(palette=["#fde68a", "#f97316", "#38bdf8", "#fefce8"], tone="light, playful, warm",
                   grade="vivid", music_style="bouncy pizzicato and ukulele"),
    "romance": dict(palette=["#3f1d2b", "#be185d", "#fbcfe8", "#fff7ed"], tone="tender, intimate",
                    grade="warm", music_style="intimate piano and strings"),
    "action": dict(palette=["#111827", "#b45309", "#f59e0b", "#e5e7eb"], tone="kinetic, high-stakes",
                   grade="teal_orange", music_style="percussive hybrid action score"),
    "fantasy": dict(palette=["#1e1b4b", "#047857", "#facc15", "#f5f5f4"], tone="mythic, adventurous",
                    grade="warm", music_style="sweeping orchestral fantasy score with choir"),
    "family": dict(palette=["#1d4ed8", "#facc15", "#f472b6", "#fefce8"], tone="heartfelt, funny, hopeful",
                   grade="pastel", music_style="whimsical orchestral score"),
    "drama": dict(palette=["#0f172a", "#334155", "#d97706", "#f1f5f9"], tone="grounded, emotional",
                  grade="teal_orange", music_style="minimal strings and piano"),
    "documentary": dict(palette=["#1f2937", "#4b5563", "#d1d5db", "#fafafa"], tone="observational, honest",
                        grade="none", music_style="ambient textures"),
}

GENRE_KEYWORDS = {
    "horror": ["haunt", "ghost", "demon", "monster", "horror", "curse", "zombie"],
    "sci-fi": ["space", "robot", "alien", "future", "planet", "ai ", "android", "galaxy", "cyber", "time travel"],
    "thriller": ["crime", "boss", "mob", "heist", "spy", "murder", "detective", "conspiracy", "kidnap", "thriller", "chase"],
    "action": ["war", "fight", "battle", "explosion", "mission", "soldier", "martial"],
    "fantasy": ["dragon", "wizard", "magic ", "sorcer", "kingdom", "quest", "sword", "fairy", "myth"],
    "romance": ["love", "romance", "wedding", "date", "heart"],
    "comedy": ["funny", "comedy", "hilarious", "prank", "silly"],
    "family": ["kid", "child", "puppy", "toy", "family", "talking animal"],
    "documentary": ["documentary", "real story", "interview"],
}

ASPECTS = {
    "2.39:1": (1280, 536),
    "1.85:1": (1280, 692),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1": (1080, 1080),
    "4:3": (960, 720),
}


def detect_genre(prompt: str) -> str:
    p = prompt.lower()
    best, score = "drama", 0
    for genre, words in GENRE_KEYWORDS.items():
        s = sum(p.count(w) for w in words)
        if s > score:
            best, score = genre, s
    return best


def build_style(medium: Medium, genre: str, aspect: str) -> StyleGuide:
    g = GENRES.get(genre, GENRES["drama"])
    w, h = ASPECTS.get(aspect, ASPECTS["16:9"])
    style = StyleGuide(medium=medium, aspect_ratio=aspect if aspect in ASPECTS else "16:9", width=w, height=h,
                       **MEDIUM_LOOKS[medium], **g)
    if medium in (Medium.animation_3d, Medium.cartoon_2d, Medium.anime, Medium.stop_motion):
        style.negative_prompt += ", photorealistic, uncanny"
    if medium == Medium.live_action:
        style.negative_prompt += ", cartoon, cgi look, plastic skin, uncanny valley"
    return style
