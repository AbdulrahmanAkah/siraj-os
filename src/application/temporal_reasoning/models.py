from dataclasses import dataclass, field


@dataclass
class TemporalReasoningPlan:
    plan_id: str
    allowed_relation_types: list[str] = field(default_factory=list)


@dataclass
class TemporalRelation:
    relation_id: str
    relation_type: str
    source_event_id: str
    target_event_id: str
    source_date: str
    target_date: str
    position: int = 0


@dataclass
class TemporalReasoningResult:
    result_id: str
    plan_id: str
    relations: list[TemporalRelation] = field(default_factory=list)
    relation_count: int = 0
    validation_state: str = "VALID"


__all__ = ["TemporalReasoningPlan", "TemporalRelation", "TemporalReasoningResult"]
