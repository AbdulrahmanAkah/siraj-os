from dataclasses import dataclass, field


@dataclass
class CausalReasoningPlan:
    plan_id: str
    allowed_relation_types: list[str] = field(default_factory=list)


@dataclass
class CausalCandidate:
    candidate_id: str
    relation_type: str
    cause_text: str
    effect_text: str
    source_claim_id: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class CausalRelation:
    relation_id: str
    relation_type: str
    cause_text: str
    effect_text: str
    source_claim_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    position: int = 0


@dataclass
class CausalReasoningResult:
    result_id: str
    plan_id: str
    candidates: list[CausalCandidate] = field(default_factory=list)
    relations: list[CausalRelation] = field(default_factory=list)
    relation_count: int = 0
    validation_state: str = "VALID"


__all__ = [
    "CausalCandidate",
    "CausalReasoningPlan",
    "CausalReasoningResult",
    "CausalRelation",
]
