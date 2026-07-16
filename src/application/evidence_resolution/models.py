from dataclasses import dataclass, field


@dataclass
class EvidenceReference:
    reference_id: str
    evidence_id: str
    source_type: str
    source_id: str


@dataclass
class EvidenceBundle:
    bundle_id: str
    evidence_ids: list[str] = field(default_factory=list)
    source_references: list[EvidenceReference] = field(default_factory=list)


@dataclass
class EvidenceResolutionPlan:
    plan_id: str
    allowed_source_types: list[str] = field(default_factory=list)
    validation_level: str = "STANDARD"


@dataclass
class ResolvedEvidence:
    resolved_evidence_id: str
    evidence_text: str
    references: list[EvidenceReference] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)


@dataclass
class EvidenceResolutionResult:
    result_id: str
    plan_id: str
    resolved_evidence: list[ResolvedEvidence] = field(default_factory=list)
    bundles: list[EvidenceBundle] = field(default_factory=list)
    evidence_count: int = 0
    bundle_count: int = 0
    validation_state: str = "VALID"


__all__ = [
    "EvidenceBundle",
    "EvidenceReference",
    "EvidenceResolutionPlan",
    "EvidenceResolutionResult",
    "ResolvedEvidence",
]
