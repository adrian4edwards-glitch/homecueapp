"""Core data model.

Everything the studio generates is derived from a single source of truth: the
StoryBible (characters, locations, props, style guide) plus the Screenplay
(scenes -> shots). Every generated clip, line of dialogue and music cue is
compiled from these records, which is what keeps characters, wardrobe,
palette, tone and camera language consistent across a full-length film.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def digest(*parts: object) -> str:
    """Stable short hash (unlike hash(), identical across processes)."""
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- enums
class Medium(str, Enum):
    live_action = "live_action"      # photoreal, human-like actors
    animation_3d = "animation_3d"    # feature-animation look (stylised 3D)
    cartoon_2d = "cartoon_2d"
    anime = "anime"
    stop_motion = "stop_motion"
    motion_graphics = "motion_graphics"


class ShotSize(str, Enum):
    EWS = "extreme wide shot"
    WS = "wide shot"
    FS = "full shot"
    MS = "medium shot"
    MCU = "medium close-up"
    CU = "close-up"
    ECU = "extreme close-up"
    OTS = "over-the-shoulder shot"
    POV = "point-of-view shot"
    TWO = "two shot"
    INSERT = "insert shot"


class CameraAngle(str, Enum):
    eye = "eye level"
    low = "low angle"
    high = "high angle"
    dutch = "dutch angle"
    birds_eye = "bird's-eye view"
    worms_eye = "worm's-eye view"
    overhead = "overhead"


class CameraMove(str, Enum):
    static = "static"
    pan_left = "pan left"
    pan_right = "pan right"
    tilt_up = "tilt up"
    tilt_down = "tilt down"
    dolly_in = "dolly in"
    dolly_out = "dolly out"
    truck_left = "truck left"
    truck_right = "truck right"
    crane_up = "crane up"
    crane_down = "crane down"
    handheld = "handheld"
    steadicam = "steadicam follow"
    orbit = "orbit"
    zoom_in = "slow zoom in"
    zoom_out = "slow zoom out"


class Transition(str, Enum):
    cut = "cut"
    dissolve = "dissolve"
    fade_black = "fadeblack"
    fade_white = "fadewhite"
    wipe_left = "wipeleft"
    wipe_right = "wiperight"
    slide_left = "slideleft"
    circle_open = "circleopen"
    smash_cut = "smash_cut"


class Status(str, Enum):
    planned = "planned"
    queued = "queued"
    generating = "generating"
    ready = "ready"
    approved = "approved"
    failed = "failed"


# --------------------------------------------------------------------------- bible
class VoiceProfile(BaseModel):
    voice_id: str = "default"          # id understood by the TTS backend
    gender: str = "neutral"
    age: str = "adult"
    accent: str = ""
    timbre: str = "warm"
    pitch: float = 1.0                 # relative; used by placeholder TTS
    rate: float = 1.0
    reference_audio: Optional[str] = None  # voice-clone sample for XTTS/F5-style models


class Character(BaseModel):
    id: str = Field(default_factory=lambda: new_id("chr"))
    name: str
    role: str = "supporting"           # lead | antagonist | supporting | extra
    description: str = ""              # canonical physical description (never changes)
    wardrobe: str = ""                 # default costume
    personality: str = ""
    motivation: str = ""
    arc: str = ""                      # character development across the film
    mannerisms: str = ""               # direction notes the actor/model must keep
    voice: VoiceProfile = Field(default_factory=VoiceProfile)
    reference_images: list[str] = []   # identity refs (IP-Adapter / face-ID / i2v keyframes)
    identity_seed: int = 0
    lora: Optional[str] = None         # trained identity LoRA name, if any
    color: str = "#8b5cf6"


class Location(BaseModel):
    id: str = Field(default_factory=lambda: new_id("loc"))
    name: str
    interior: bool = True
    description: str = ""
    set_dressing: str = ""             # mise-en-scene: what is always in this set
    lighting: str = ""
    reference_images: list[str] = []
    seed: int = 0


class Prop(BaseModel):
    id: str = Field(default_factory=lambda: new_id("prp"))
    name: str
    description: str = ""
    owner_id: Optional[str] = None
    reference_images: list[str] = []


class StyleGuide(BaseModel):
    medium: Medium = Medium.live_action
    look: str = "cinematic Hollywood feature film"
    palette: list[str] = ["#0f172a", "#1e3a8a", "#f59e0b", "#e2e8f0"]
    tone: str = "dramatic"
    lighting_style: str = "motivated naturalistic lighting, soft key, deep shadows"
    lens_package: str = "anamorphic prime lenses"
    film_stock: str = "35mm film grain"
    aspect_ratio: str = "2.39:1"
    width: int = 1280
    height: int = 536
    fps: int = 24
    music_style: str = "orchestral score"
    grade: str = "teal_orange"         # teal_orange | warm | cool | noir | pastel | vivid | none
    lut_path: Optional[str] = None
    negative_prompt: str = (
        "deformed, extra fingers, mutated hands, disfigured face, identity drift, "
        "inconsistent outfit, flicker, watermark, text, logo, low quality, blurry"
    )


class StoryBible(BaseModel):
    title: str = "Untitled"
    logline: str = ""
    genre: str = "drama"
    theme: str = ""
    synopsis: str = ""
    outline: list[str] = []            # act / beat outline
    style: StyleGuide = Field(default_factory=StyleGuide)
    characters: list[Character] = []
    locations: list[Location] = []
    props: list[Prop] = []

    def character(self, cid: str) -> Optional[Character]:
        return next((c for c in self.characters if c.id == cid), None)

    def location(self, lid: str) -> Optional[Location]:
        return next((l for l in self.locations if l.id == lid), None)

    def prop(self, pid: str) -> Optional[Prop]:
        return next((p for p in self.props if p.id == pid), None)


# --------------------------------------------------------------------------- screenplay
class DialogueLine(BaseModel):
    id: str = Field(default_factory=lambda: new_id("dlg"))
    character_id: str
    text: str
    parenthetical: str = ""            # (whispering), (beat), ...
    emotion: str = "neutral"
    offset: float = 0.3                # seconds into the shot
    audio_path: Optional[str] = None
    duration: Optional[float] = None


class SoundCue(BaseModel):
    id: str = Field(default_factory=lambda: new_id("sfx"))
    description: str
    kind: str = "sfx"                  # sfx | ambience | foley
    offset: float = 0.0
    duration: float = 2.0
    volume: float = 0.6
    audio_path: Optional[str] = None


class Shot(BaseModel):
    id: str = Field(default_factory=lambda: new_id("sht"))
    number: str = "1A"
    size: ShotSize = ShotSize.MS
    angle: CameraAngle = CameraAngle.eye
    movement: CameraMove = CameraMove.static
    lens_mm: int = 35
    duration: float = 4.0
    action: str = ""                   # what happens on screen
    blocking: str = ""                 # character direction / staging
    mise_en_scene: str = ""
    lighting: str = ""
    character_ids: list[str] = []
    prop_ids: list[str] = []
    wardrobe_overrides: dict[str, str] = {}  # character_id -> costume for this shot (explicit change)
    dialogue: list[DialogueLine] = []
    sounds: list[SoundCue] = []
    screen_direction: str = "neutral"  # left_to_right | right_to_left | neutral (180-degree rule)
    transition_in: Transition = Transition.cut
    seed: Optional[int] = None
    status: Status = Status.planned
    prompt: str = ""                   # last compiled prompt
    clip_path: Optional[str] = None
    keyframe_path: Optional[str] = None
    takes: list[str] = []              # previous generations
    gen_key: str = ""                  # hash of the request that produced clip_path (cache key)
    error: str = ""
    notes: str = ""


class Scene(BaseModel):
    id: str = Field(default_factory=lambda: new_id("scn"))
    number: int = 1
    heading: str = "INT. LOCATION - DAY"
    location_id: Optional[str] = None
    time_of_day: str = "DAY"
    beat: str = ""                     # which outline beat this serves
    summary: str = ""
    mood: str = ""
    color_mood: str = ""
    music_cue: str = ""
    music_path: Optional[str] = None
    ambience: str = ""
    transition_out: Transition = Transition.cut
    shots: list[Shot] = []

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.shots)


# --------------------------------------------------------------------------- edit / mix
class TrackMix(BaseModel):
    volume: float = 1.0
    mute: bool = False


class MixSettings(BaseModel):
    dialogue: TrackMix = TrackMix(volume=1.0)
    music: TrackMix = TrackMix(volume=0.35)
    sfx: TrackMix = TrackMix(volume=0.6)
    ducking: bool = True               # sidechain-duck music under dialogue
    duck_amount: float = 8.0           # compressor ratio
    loudness_lufs: float = -16.0       # -16 web / -24 broadcast / -27 theatrical-ish
    burn_subtitles: bool = False


class GradeSettings(BaseModel):
    preset: str = "auto"               # auto = from style guide
    grain: bool = True
    vignette: bool = True
    letterbox: bool = True


class RenderOutput(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rnd"))
    created: float = Field(default_factory=time.time)
    video_path: str
    subtitles_path: Optional[str] = None
    edl_path: Optional[str] = None
    duration: float = 0.0
    scope: str = "film"


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("prj"))
    created: float = Field(default_factory=time.time)
    updated: float = Field(default_factory=time.time)
    prompt: str = ""
    bible: StoryBible = Field(default_factory=StoryBible)
    scenes: list[Scene] = []
    mix: MixSettings = Field(default_factory=MixSettings)
    grade: GradeSettings = Field(default_factory=GradeSettings)
    renders: list[RenderOutput] = []

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.scenes)

    def find_shot(self, shot_id: str) -> tuple[Optional[Scene], Optional[Shot]]:
        for sc in self.scenes:
            for sh in sc.shots:
                if sh.id == shot_id:
                    return sc, sh
        return None, None

    def find_scene(self, scene_id: str) -> Optional[Scene]:
        return next((s for s in self.scenes if s.id == scene_id), None)


class CreateRequest(BaseModel):
    prompt: str
    title: Optional[str] = None
    medium: Medium = Medium.live_action
    genre: Optional[str] = None
    target_minutes: float = 3.0        # 90+ for a feature
    aspect_ratio: str = "2.39:1"
    characters: list[str] = []         # optional "Name: description" seeds
