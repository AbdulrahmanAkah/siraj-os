"""Versioned provenance-first contracts for the Shamela extraction pilot."""

from __future__ import annotations

from dataclasses import dataclass, field


ENTITY_TYPES = (
    "PERSON",
    "PROPHET",
    "COMPANION",
    "CALIPH",
    "RULER",
    "SCHOLAR",
    "NARRATOR",
    "AUTHOR",
    "GROUP",
    "TRIBE",
    "DYNASTY",
    "STATE",
    "SECT",
    "PLACE",
    "CITY",
    "REGION",
    "WORK",
    "EVENT",
    "PERIOD",
    "CONCEPT",
)

RELATION_TYPES = (
    "PARENT_OF",
    "CHILD_OF",
    "DESCENDANT_OF",
    "TEACHER_OF",
    "STUDENT_OF",
    "NARRATED_FROM",
    "AUTHORED",
    "MEMBER_OF",
    "LED",
    "RULED",
    "FOUNDED",
    "FOUGHT",
    "ALLIED_WITH",
    "OPPOSED",
    "LIVED_IN",
    "TRAVELED_TO",
    "BORN_IN",
    "DIED_IN",
    "PARTICIPATED_IN",
    "MENTIONED_IN",
    "CONTEMPORARY_WITH",
    "PRECEDED",
    "SUCCEEDED",
)


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class EntityMention:
    mention_id: str
    source_id: str
    locator: str
    segment_id: int
    original_text_span: TextSpan
    normalized_surface_form: str
    entity_type_candidate: list[str]
    extraction_confidence: float
    extractor_version: str
    mention_context: str = "BODY"
    rule_id: str = ""


@dataclass(frozen=True)
class CanonicalEntityCandidate:
    candidate_id: str
    canonical_name: str
    entity_type: list[str]
    aliases: list[str]
    linked_mentions: list[str]
    merge_confidence: float
    review_status: str
    rule_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EventMention:
    event_mention_id: str
    source_id: str
    locator: str
    segment_id: int
    original_text_span: TextSpan
    event_type: str
    participants: list[str]
    places: list[str]
    temporal_expression: str
    temporal_precision: str
    extraction_confidence: float
    rule_id: str = ""


@dataclass(frozen=True)
class HistoricalClaim:
    claim_id: str
    source_id: str
    locator: str
    segment_id: int
    original_text: str
    original_text_span: TextSpan
    normalized_claim: str
    subject: str
    predicate: str
    object: str
    claim_modality: str
    historical_confidence: str
    extraction_confidence: float
    review_status: str
    evidence_id: str
    rule_id: str = ""


@dataclass(frozen=True)
class RelationMention:
    relation_id: str
    subject_mention: str
    relation_type: str
    object_mention: str
    source_id: str
    locator: str
    segment_id: int
    evidence_span: TextSpan
    extraction_confidence: float
    rule_id: str = ""


@dataclass(frozen=True)
class IsnadNarrator:
    mention_id: str
    position: int
    connector: str


@dataclass(frozen=True)
class IsnadChain:
    chain_id: str
    source_id: str
    locator: str
    segment_id: int
    evidence_span: TextSpan
    narrators: list[IsnadNarrator]
    relation_ids: list[str]
    validation_status: str = "UNASSESSED_TRANSMISSION"


@dataclass(frozen=True)
class TemporalMention:
    temporal_id: str
    source_id: str
    locator: str
    segment_id: int
    original_text_span: TextSpan
    normalized_value: str
    calendar: str
    temporal_type: str
    temporal_precision: str
    conversion_status: str = "NOT_CONVERTED"
    rule_id: str = ""


__all__ = [
    "CanonicalEntityCandidate",
    "ENTITY_TYPES",
    "EntityMention",
    "EventMention",
    "HistoricalClaim",
    "IsnadChain",
    "IsnadNarrator",
    "RELATION_TYPES",
    "RelationMention",
    "TemporalMention",
    "TextSpan",
]
