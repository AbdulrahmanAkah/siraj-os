from dataclasses import dataclass, field


@dataclass
class Scene:
    scene_id: str
    block_id: str
    scene_type: str
    visual_role: str
    estimated_duration: int
    position: int


@dataclass
class ScenePlan:
    plan_id: str
    narration_plan_id: str
    scenes: list[Scene] = field(default_factory=list)
    total_duration: int = 0
    scene_count: int = 0


__all__ = ["Scene", "ScenePlan"]
