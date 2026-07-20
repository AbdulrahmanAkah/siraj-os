"""Versioned contracts for local, evidence-bound semantic extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SEMANTIC_SCHEMA_VERSION = "siraj-local-semantic-v2"
PROMPT_VERSION = "local-semantic-prompts-v8"
STAGES = (
    "STRUCTURAL_ANALYSIS",
    "MENTION_EXTRACTION",
    "EVENT_RELATION_EXTRACTION",
    "CLAIM_ATTRIBUTION",
    "DETERMINISTIC_EVIDENCE_VALIDATION",
    "CRITICAL_REVIEW",
    "RECONCILIATION",
    "LEARNING_REPORT",
)
RECONCILIATION_STATUSES = (
    "ACCEPTED_HIGH_CONFIDENCE",
    "ACCEPTED_WITH_WARNING",
    "HUMAN_REVIEW_REQUIRED",
    "REJECTED_UNSUPPORTED",
)


@dataclass(frozen=True)
class EvidenceSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ProviderIdentity:
    provider_id: str
    model_id: str
    model_digest: str = "UNRESOLVED"
    prompt_version: str = PROMPT_VERSION
    schema_version: str = SEMANTIC_SCHEMA_VERSION


@dataclass(frozen=True)
class SemanticHardwareProfile:
    concurrency: int = 1
    context_tokens: int = 1536
    maximum_output_tokens: int = 700
    stage_timeout_seconds: float = 900.0
    keep_alive: str = "10m"
    checkpoint_after_each_stage: bool = True


@dataclass(frozen=True)
class SemanticProviderHealth:
    status: str
    provider: ProviderIdentity
    reason_code: str
    localhost_only: bool = True


@dataclass(frozen=True)
class StructuralClassification:
    segment_type: str
    subtypes: list[str] = field(default_factory=list)
    heading_ranges: list[EvidenceSpan] = field(default_factory=list)
    prose_ranges: list[EvidenceSpan] = field(default_factory=list)
    poetry_ranges: list[EvidenceSpan] = field(default_factory=list)
    isnad_ranges: list[EvidenceSpan] = field(default_factory=list)
    matn_ranges: list[EvidenceSpan] = field(default_factory=list)
    footnote_ranges: list[EvidenceSpan] = field(default_factory=list)
    quoted_source_ranges: list[EvidenceSpan] = field(default_factory=list)
    requires_previous_context: bool = False
    requires_next_context: bool = False
    confidence: float = 0.0
    rationale_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EntityMentionV2:
    mention_id: str
    exact_surface: str
    start: int
    end: int
    normalized_surface: str
    entity_types: list[str]
    contextual_roles: list[str]
    evidence: EvidenceSpan
    uncertainty: str
    source_id: str
    locator: str


@dataclass(frozen=True)
class EventParticipantV2:
    mention_reference: str = ""
    exact_surface: str = ""
    role: str = "UNSPECIFIED"


@dataclass(frozen=True)
class EventPlaceV2:
    mention_reference: str = ""
    exact_surface: str = ""
    role: str = "LOCATION"


@dataclass(frozen=True)
class EventV2:
    event_id: str
    event_type: str
    trigger: EvidenceSpan
    participants: list[EventParticipantV2] = field(default_factory=list)
    places: list[EventPlaceV2] = field(default_factory=list)
    institutions_offices: list[str] = field(default_factory=list)
    temporal_links: list[str] = field(default_factory=list)
    causes: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)
    modality: str = "SOURCE_REPORTED"
    attribution: list[str] = field(default_factory=list)
    uncertainty: str = "UNVERIFIED_SOURCE_REPORT"


@dataclass(frozen=True)
class RelationV2:
    relation_id: str
    subject_mention: str
    predicate: str
    object_reference: str
    evidence: EvidenceSpan
    explicit_or_inferred: str
    attribution: list[str]
    confidence: float


@dataclass(frozen=True)
class ClaimV2:
    claim_id: str
    proposition: str
    speaker_or_source: str
    quoted_or_authorial: str
    assertion_status: str
    evidence: EvidenceSpan
    source_attribution_chain: list[str]


@dataclass(frozen=True)
class IsnadNarratorV2:
    mention_id: str
    position: int
    transition: str


@dataclass(frozen=True)
class IsnadV2:
    isnad_id: str
    ordered_narrators: list[IsnadNarratorV2]
    exact_chain_range: EvidenceSpan
    matn_boundary: int | None
    ambiguous_transitions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TemporalV2:
    temporal_id: str
    exact_expression: str
    evidence: EvidenceSpan
    calendar: str
    precision: str
    relative_reference: str = ""
    offset: str = ""
    unresolved_reference: bool = False


@dataclass(frozen=True)
class InstitutionOfficeV2:
    record_id: str
    institution: str
    office: str
    holder_mention_id: str
    action: str
    evidence: EvidenceSpan
    attribution: list[str]


@dataclass(frozen=True)
class SemanticSegmentInput:
    audit_segment_id: str
    source_id: str
    locator: str
    original_text: str
    book_id: int
    book_title: str
    segment_id: int
    current_extraction: dict[str, Any]
    reviewer_notes: str = ""
    selection_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str
    payload: dict[str, Any]
    input_hash: str
    output_hash: str
    reason_codes: list[str]
    cache_hit: bool = False
    latency_ms: int | None = None
    tokens: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationIssue:
    issue_id: str
    code: str
    severity: str
    subject_id: str
    detail: str = ""


@dataclass(frozen=True)
class ReconciliationItem:
    item_id: str
    item_type: str
    status: str
    reason_codes: list[str]
    baseline_ids: list[str] = field(default_factory=list)
    model_ids: list[str] = field(default_factory=list)
    evidence: EvidenceSpan | None = None


class SemanticProviderError(RuntimeError):
    """A normalized local semantic-provider failure."""

    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.details = dict(details or {})


__all__ = [
    "ClaimV2",
    "EntityMentionV2",
    "EvidenceSpan",
    "EventParticipantV2",
    "EventPlaceV2",
    "EventV2",
    "InstitutionOfficeV2",
    "IsnadNarratorV2",
    "IsnadV2",
    "PROMPT_VERSION",
    "ProviderIdentity",
    "RECONCILIATION_STATUSES",
    "ReconciliationItem",
    "SEMANTIC_SCHEMA_VERSION",
    "STAGES",
    "SemanticHardwareProfile",
    "SemanticProviderError",
    "SemanticProviderHealth",
    "SemanticSegmentInput",
    "StageResult",
    "StructuralClassification",
    "TemporalV2",
    "RelationV2",
    "ValidationIssue",
]
