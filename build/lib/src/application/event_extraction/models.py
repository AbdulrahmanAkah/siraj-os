from dataclasses import dataclass, field


@dataclass
class EventCandidate:
    candidate_id: str
    event_type: str
    event_title: str
    event_date: str | None
    source_claim_ids: list[str] = field(default_factory=list)
    source_entity_ids: list[str] = field(default_factory=list)
    extraction_strategy: str = ""


@dataclass
class EventEvidence:
    evidence_id: str
    supporting_text: str
    claim_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)


@dataclass
class EventRecord:
    event_id: str
    event_type: str
    event_title: str
    event_date: str | None
    source_claim_ids: list[str] = field(default_factory=list)
    source_entity_ids: list[str] = field(default_factory=list)
    evidence: list[EventEvidence] = field(default_factory=list)


@dataclass
class EventExtractionPlan:
    plan_id: str
    claim_extraction_result_id: str
    entity_extraction_result_id: str
    extraction_strategies: list[str] = field(default_factory=list)
    event_limit: int = 100
    validation_rules: list[str] = field(default_factory=list)


@dataclass
class EventExtractionResult:
    result_id: str
    plan_id: str
    candidates: list[EventCandidate] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    candidate_count: int = 0
    event_count: int = 0


__all__ = [
    "EventCandidate",
    "EventEvidence",
    "EventExtractionPlan",
    "EventExtractionResult",
    "EventRecord",
]
