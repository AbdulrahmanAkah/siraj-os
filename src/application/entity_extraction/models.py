from dataclasses import dataclass, field


@dataclass
class EntityCandidate:
    candidate_id: str
    source_claim_id: str
    entity_name: str
    entity_type: str
    extraction_strategy: str


@dataclass
class EntityEvidence:
    evidence_id: str
    claim_id: str
    supporting_text: str


@dataclass
class EntityRecord:
    entity_id: str
    entity_name: str
    entity_type: str
    source_claim_ids: list[str] = field(default_factory=list)
    evidence: list[EntityEvidence] = field(default_factory=list)


@dataclass
class EntityExtractionPlan:
    plan_id: str
    claim_extraction_result_id: str
    extraction_strategies: list[str] = field(default_factory=list)
    entity_limit: int = 100
    validation_rules: list[str] = field(default_factory=list)


@dataclass
class EntityExtractionResult:
    result_id: str
    plan_id: str
    candidates: list[EntityCandidate] = field(default_factory=list)
    entities: list[EntityRecord] = field(default_factory=list)
    candidate_count: int = 0
    entity_count: int = 0


__all__ = [
    "EntityCandidate",
    "EntityEvidence",
    "EntityExtractionPlan",
    "EntityExtractionResult",
    "EntityRecord",
]
