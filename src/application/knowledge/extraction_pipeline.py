from .entity_extractor import EntityExtractor
from .event_extractor import EventExtractor
from .claim_extractor import ClaimExtractor
from .relationship_extractor import RelationshipExtractor
from .source_extractor import SourceExtractor
from .evidence_extractor import EvidenceExtractor
from .location_extractor import LocationExtractor

from .quality_engine import QualityEngine
from .object_mapper import ObjectMapper
from .object_merger import ObjectMerger
from .object_collector import ObjectCollector
from .entity_resolver import EntityResolver
from .relationship_resolver import RelationshipResolver
from .knowledge_quality_engine import KnowledgeQualityEngine
from .graph_builder import GraphBuilder
from .graph_normalizer import GraphNormalizer
from .graph_merger import GraphMerger
from .entity_canonicalizer import EntityCanonicalizer
from .event_canonicalizer import EventCanonicalizer
from .graph_validator import GraphIntegrityValidator
from .entity_canonicalizer import EntityCanonicalizer

from .document_parser import DocumentParser
from .context_builder import ContextBuilder


class ExtractionPipeline:

    def __init__(self):

        self.document_parser = DocumentParser()
        self.context_builder = ContextBuilder()

        self.extractors = [
            EntityExtractor(),
            EventExtractor(),
            ClaimExtractor(),
            RelationshipExtractor(),
            SourceExtractor(),
            EvidenceExtractor(),
            LocationExtractor(),
        ]

        self.quality = QualityEngine()
        self.mapper=ObjectMapper()
        self.object_merger=ObjectMerger()
        self.collector=ObjectCollector()
        self.resolver=EntityResolver()
        self.relationship_resolver=RelationshipResolver()
        self.knowledge_quality = KnowledgeQualityEngine()
        self.graph_builder = GraphBuilder()
        self.graph_normalizer = GraphNormalizer()
        self.graph_merger = GraphMerger()
        self.entity_canonicalizer = EntityCanonicalizer()
        self.event_canonicalizer = EventCanonicalizer()
        self.graph_validator = GraphIntegrityValidator()

    def run(
        self,
        text: str,
        document_name: str = "",
        source: str = "",
        language: str = "",
    ):

        document = self.document_parser.parse(
            text=text,
            document_name=document_name,
            source=source,
            language=language,
        )

        contexts = self.context_builder.build(document)

        candidates = []

        for context in contexts:

            for extractor in self.extractors:

                try:
                    candidates.extend(extractor.extract(context))

                except Exception as e:
                    print(f"[Extractor Error] {extractor.__class__.__name__}: {e}")

        candidates = self.quality.process(candidates)

        objects = []

        for candidate in candidates:

            obj = self.mapper.map(candidate)

            if obj is not None:
                objects.append(obj)

        extraction = self.collector.collect(objects)

        extraction = self.object_merger.merge(extraction)

        extraction=self.resolver.resolve(extraction)

        extraction=self.relationship_resolver.resolve(extraction)
        extraction=self.graph_normalizer.normalize(extraction)

        extraction=self.knowledge_quality.process(extraction)

        graph=self.graph_builder.build(extraction)
        graph = self.entity_canonicalizer.run(graph)
        graph = self.event_canonicalizer.run(graph)
        graph = self.graph_merger.merge(graph)
        graph = self.graph_validator.validate(graph)

        return graph










