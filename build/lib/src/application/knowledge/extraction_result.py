from dataclasses import dataclass, field

from src.domain.knowledge_objects.person import Person
from src.domain.knowledge_objects.event import Event
from src.domain.knowledge_objects.location import Location
from src.domain.knowledge_objects.claim import Claim
from src.domain.knowledge_objects.source import Source
from src.domain.knowledge_objects.statistic import Statistic
from src.domain.knowledge_objects.timeline_event import TimelineEvent
from src.domain.knowledge_objects.relationship import Relationship
from src.domain.knowledge_objects.document_reference import DocumentReference
from src.domain.knowledge_objects.evidence_reference import EvidenceReference
from src.domain.knowledge_objects.claim_evidence import ClaimEvidence


@dataclass
class ExtractionResult:

    persons: list[Person] = field(default_factory=list)

    events: list[Event] = field(default_factory=list)

    locations: list[Location] = field(default_factory=list)

    claims: list[Claim] = field(default_factory=list)

    statistics: list[Statistic] = field(default_factory=list)

    timeline: list[TimelineEvent] = field(default_factory=list)

    relationships: list[Relationship] = field(default_factory=list)

    sources: list[Source] = field(default_factory=list)

    documents: list[DocumentReference] = field(default_factory=list)

    evidence: list[EvidenceReference] = field(default_factory=list)

    claim_evidence: list[ClaimEvidence] = field(default_factory=list)


__all__ = ["ExtractionResult"]


