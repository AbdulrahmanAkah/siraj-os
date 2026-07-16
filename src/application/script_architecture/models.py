from dataclasses import dataclass, field


@dataclass
class ScriptSegment:
    segment_id: str
    beat_id: str
    segment_type: str
    purpose: str
    estimated_duration: float
    position: int


@dataclass
class ScriptStructure:
    structure_id: str
    narrative_architecture_id: str
    segments: list[ScriptSegment] = field(default_factory=list)
    estimated_runtime: float = 0.0
    segment_count: int = 0


__all__ = ["ScriptSegment", "ScriptStructure"]
