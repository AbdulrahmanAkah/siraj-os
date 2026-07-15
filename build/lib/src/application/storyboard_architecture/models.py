from dataclasses import dataclass, field


@dataclass
class StoryboardFrame:
    frame_id: str
    scene_id: str
    frame_type: str
    composition_role: str
    duration_seconds: int
    position: int


@dataclass
class StoryboardSequence:
    sequence_id: str
    scene_id: str
    frames: list[StoryboardFrame] = field(default_factory=list)


@dataclass
class StoryboardArchitecture:
    architecture_id: str
    scene_plan_id: str
    sequences: list[StoryboardSequence] = field(default_factory=list)
    frame_count: int = 0
    total_duration: int = 0


__all__ = [
    "StoryboardArchitecture",
    "StoryboardFrame",
    "StoryboardSequence",
]
