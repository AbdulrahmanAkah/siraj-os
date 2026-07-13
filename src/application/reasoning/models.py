from dataclasses import dataclass, field


@dataclass
class ClaimCluster:
    cluster_id: str
    claim_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)


@dataclass
class SupportProfile:
    claim_id: str
    evidence_count: int
    source_count: int
    document_count: int
    confidence_score: float
    confidence_signals: list[str] = field(default_factory=list)


@dataclass
class ContradictionRecord:
    claim_a: str
    claim_b: str
    reason: str
    confidence: float


__all__ = ["ClaimCluster", "SupportProfile", "ContradictionRecord"]
