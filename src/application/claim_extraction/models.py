from dataclasses import dataclass, field

from src.application.knowledge_repository.models import KnowledgeRecord


@dataclass
class ClaimCandidate:
    candidate_id: str
    source_record_id: str
    claim_text: str
    extraction_strategy: str


@dataclass
class ClaimEvidence:
    evidence_id: str
    record_id: str
    fingerprint: str
    supporting_text: str


@dataclass
class ClaimRecord:
    claim_id: str
    claim_text: str
    evidence: list[ClaimEvidence] = field(default_factory=list)
    source_record_ids: list[str] = field(default_factory=list)


@dataclass
class ClaimExtractionPlan:
    plan_id: str
    retrieval_id: str
    extraction_strategies: list[str] = field(default_factory=list)
    claim_limit: int = 100
    validation_rules: list[str] = field(default_factory=list)


@dataclass
class ClaimExtractionResult:
    result_id: str
    plan_id: str
    claims: list[ClaimRecord] = field(default_factory=list)
    candidates: list[ClaimCandidate] = field(default_factory=list)
    claim_count: int = 0
    candidate_count: int = 0


__all__ = [
    "ClaimCandidate",
    "ClaimEvidence",
    "ClaimExtractionPlan",
    "ClaimExtractionResult",
    "ClaimRecord",
]
