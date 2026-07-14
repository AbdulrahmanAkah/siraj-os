from dataclasses import dataclass, field


@dataclass
class NarrationBlock:
    block_id: str
    segment_id: str
    narration_role: str
    information_priority: str
    estimated_word_count: int
    position: int


@dataclass
class NarrationPlan:
    plan_id: str
    script_structure_id: str
    blocks: list[NarrationBlock] = field(default_factory=list)
    estimated_total_words: int = 0
    estimated_duration_seconds: float = 0.0


__all__ = ["NarrationBlock", "NarrationPlan"]
