from dataclasses import dataclass, field


@dataclass
class NarrativeReasoningPlan:
    plan_id: str
    narrative_roles: list[str] = field(default_factory=list)


@dataclass
class NarrativeReasoningRecord:
    record_id: str
    event_id: str
    role: str
    reasoning_chain_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    position: int = 0


@dataclass
class NarrativeReasoningResult:
    result_id: str
    plan_id: str
    records: list[NarrativeReasoningRecord] = field(default_factory=list)
    record_count: int = 0
    validation_state: str = "VALID"


__all__ = [
    "NarrativeReasoningPlan",
    "NarrativeReasoningRecord",
    "NarrativeReasoningResult",
]
