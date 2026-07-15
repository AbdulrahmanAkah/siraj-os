from dataclasses import dataclass, field


@dataclass
class HistoricalReasoningPlan:
    plan_id: str
    validation_rules: list[str] = field(default_factory=list)


@dataclass
class ReasoningCandidate:
    candidate_id: str
    event_id: str
    statement: str
    graph_node_id: str
    evidence_ids: list[str] = field(default_factory=list)
    confidence_record_ids: list[str] = field(default_factory=list)
    source_claim_ids: list[str] = field(default_factory=list)
    source_entity_ids: list[str] = field(default_factory=list)
    position: int = 0


@dataclass
class ReasoningChain:
    chain_id: str
    candidates: list[ReasoningCandidate] = field(default_factory=list)
    source_event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    position: int = 0


@dataclass
class ReasoningResult:
    result_id: str
    plan_id: str
    chains: list[ReasoningChain] = field(default_factory=list)
    chain_count: int = 0
    validation_state: str = "VALID"


__all__ = [
    "HistoricalReasoningPlan",
    "ReasoningCandidate",
    "ReasoningChain",
    "ReasoningResult",
]
