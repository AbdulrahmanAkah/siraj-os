from dataclasses import dataclass, field


@dataclass
class ClaimScore:
    claim_id: str
    score: float
    support_score: float
    source_score: float
    evidence_score: float
    contradiction_penalty: float


@dataclass
class SelectionProfile:
    claim_id: str
    final_score: float
    reasons: list[str] = field(default_factory=list)
    support_summary: str = ""
    contradiction_summary: str = ""


__all__ = ["ClaimScore", "SelectionProfile"]
