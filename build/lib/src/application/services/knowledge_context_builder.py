from src.application.models.knowledge_context import KnowledgeContext
from src.application.models.outline import Outline


class KnowledgeContextBuilder:
    def build(self, outline: Outline) -> KnowledgeContext:
        return KnowledgeContext(
            primary_topic=outline.title,
            description=outline.description,
            key_entities=list(outline.entities),
            verified_claims=list(outline.claims),
            supporting_sources=list(outline.sources),
            metadata={},
        )


__all__ = ["KnowledgeContextBuilder"]


