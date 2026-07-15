from dataclasses import dataclass, field

@dataclass
class CorrelationCandidate:
    candidate_id: str
    correlation_type: str
    correlation_key: str
    source_ids: list[str] = field(default_factory=list)

@dataclass
class CorrelationGroup:
    group_id: str
    correlation_type: str
    correlation_key: str
    source_ids: list[str] = field(default_factory=list)

@dataclass
class CorrelationPlan:
    plan_id: str
    allowed_correlation_types: list[str] = field(default_factory=list)

@dataclass
class CorrelationResult:
    result_id: str
    plan_id: str
    groups: list[CorrelationGroup] = field(default_factory=list)
    group_count: int = 0
    validation_state: str = "VALID"
