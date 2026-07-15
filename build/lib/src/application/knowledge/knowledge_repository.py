from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from src.application.knowledge_v2.pipeline import KnowledgeExtractionPipeline
from src.application.knowledge.graph_builder import GraphBuilder
from src.application.knowledge.extraction_result import ExtractionResult
from src.application.knowledge.object_mapper import ObjectMapper
from src.application.knowledge.canonicalizer import Canonicalizer
from src.domain.knowledge_objects.claim import Claim
from src.domain.knowledge_objects.event import Event
from src.domain.knowledge_objects.location import Location
from src.domain.knowledge_objects.relationship import Relationship
from src.domain.knowledge_objects.source import Source
from src.domain.knowledge_objects.statistic import Statistic
from src.domain.knowledge_objects.timeline_event import TimelineEvent
from src.domain.knowledge_objects.document_reference import DocumentReference
from src.domain.knowledge_objects.evidence_reference import EvidenceReference
from src.domain.knowledge_objects.claim_evidence import ClaimEvidence


@dataclass
class KnowledgeRepository:

    gateway: object | None = None
    extractions: list = field(default_factory=list)


    def __post_init__(self):

        self.extractor = KnowledgeExtractionPipeline()
        self.graph_builder = GraphBuilder()

    @staticmethod
    def _stable_id(prefix, *values):
        identity = "\x00".join(
            Canonicalizer.normalize_text(str(value)) for value in values
        )
        return f"{prefix}_{sha256(identity.encode('utf-8')).hexdigest()[:16]}"


    def ingest_text(self, text, document_title="Imported document"):

        raw_extraction = self.extractor.extract(text)
        document_id = self._stable_id("document", text)

        mapper = ObjectMapper()
        entities = raw_extraction.get("entities", [])
        event_entity_values = {
            candidate.value.lower()
            for candidate in entities
            if candidate.kind == "EVENT"
        }

        def map_entity(candidate):
            mapped = mapper.map(candidate)
            if candidate.kind == "ORGANIZATION" and mapped is not None:
                mapped.metadata["entity_kind"] = "ORGANIZATION"
            return mapped

        sources = [
            Source(
                title=Canonicalizer.sanitize_text(item.get("name", "")),
                type=item.get("type", ""),
                url=item.get("url", ""),
                source_id=self._stable_id(
                    "source",
                    item.get("name", ""),
                    item.get("url", ""),
                    item.get("type", ""),
                ),
                metadata={"confidence": item.get("confidence", 1.0)},
            )
            for index, item in enumerate(raw_extraction.get("sources", []))
        ]
        if not sources:
            sources.append(
                Source(
                    title=Canonicalizer.sanitize_text(document_title),
                    type="document",
                    source_id=self._stable_id("source", document_title),
                )
            )

        source_ids = [source.source_id for source in sources]
        document = DocumentReference(
            document_id=document_id,
            title=Canonicalizer.sanitize_text(document_title),
            source_id=source_ids[0],
        )
        claims = []
        evidence = []
        claim_evidence = []
        for index, item in enumerate(raw_extraction.get("facts", [])):
            claim_text = Canonicalizer.sanitize_text(item.get("value", ""))
            claim_id = self._stable_id("claim", claim_text)
            evidence_id = self._stable_id(
                "evidence",
                document_id,
                index,
                claim_text,
            )
            confidence = float(item.get("confidence", 1.0))
            claims.append(
                Claim(
                    text=claim_text,
                    claim_id=claim_id,
                    source_ids=list(source_ids),
                    evidence_ids=[evidence_id],
                    confidence=confidence,
                )
            )
            evidence.append(
                EvidenceReference(
                    evidence_id=evidence_id,
                    document_id=document_id,
                    paragraph_index=0,
                    sentence_index=index,
                    text=claim_text,
                )
            )
            claim_evidence.append(
                ClaimEvidence(
                    claim_id=claim_id,
                    evidence_id=evidence_id,
                    confidence=confidence,
                )
            )

        extraction = ExtractionResult(
            persons=[
                map_entity(candidate)
                for candidate in entities
                if candidate.kind in {"PERSON", "ORGANIZATION"}
            ],
            events=[
                map_entity(candidate)
                for candidate in entities
                if candidate.kind == "EVENT"
            ] + [
                Event(name=item.get("value", ""))
                for item in raw_extraction.get("events", [])
                if not any(
                    value in item.get("value", "").lower()
                    for value in event_entity_values
                )
            ],
            locations=[
                mapper.map(candidate)
                for candidate in entities
                if candidate.kind == "LOCATION"
            ] + [
                Location(name=item.get("value", ""))
                for item in raw_extraction.get("locations", [])
            ],
            claims=claims,
            statistics=[
                Statistic(
                    value=item.get("value", ""),
                    unit=item.get("unit", ""),
                )
                for item in raw_extraction.get("statistics", [])
            ],
            timeline=[
                TimelineEvent(
                    title=Canonicalizer.sanitize_text(
                        item.get("title", item.get("value", ""))
                    ),
                    date=item.get("value", ""),
                )
                for item in raw_extraction.get("timeline", [])
            ],
            relationships=[
                Relationship(
                    subject=item.get("subject", ""),
                    predicate=item.get("predicate", ""),
                    object=item.get("object", ""),
                )
                for item in raw_extraction.get(
                    "relations",
                    raw_extraction.get("relationships", []),
                )
            ],
            sources=sources,
            documents=[document],
            evidence=evidence,
            claim_evidence=claim_evidence,
        )

        self.extractions.append(
            extraction
        )

        return self.graph_builder.build(
            self.extractions
        )


    def ingest_file(self,path):

        text = Path(path).read_text(
            encoding="utf-8"
        )

        return self.ingest_text(text, document_title=Path(path).name)


__all__ = [
    "KnowledgeRepository"
]
