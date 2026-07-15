from dataclasses import dataclass, field


@dataclass
class ClaimEvidence:
    """A non-evaluative link between a claim and supporting evidence."""

    claim_id: str = ""
    evidence_id: str = ""
    confidence: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)


__all__ = ["ClaimEvidence"]
