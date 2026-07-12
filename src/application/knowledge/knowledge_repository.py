from dataclasses import dataclass, field
from pathlib import Path

from src.application.knowledge_v2.pipeline import KnowledgeExtractionPipeline
from src.application.knowledge.graph_builder import GraphBuilder


@dataclass
class KnowledgeRepository:

    gateway: object | None = None
    extractions: list = field(default_factory=list)


    def __post_init__(self):

        self.extractor = KnowledgeExtractionPipeline()
        self.graph_builder = GraphBuilder()


    def ingest_text(self,text):

        extraction = self.extractor.extract(text)

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

        return self.ingest_text(text)


__all__ = [
    "KnowledgeRepository"
]
