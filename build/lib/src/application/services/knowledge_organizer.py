from typing import Optional

from src.application.models.knowledge_context import KnowledgeContext
from src.application.models.organized_knowledge import OrganizedKnowledge
from src.domain.knowledge_objects.relationship import Relationship


class KnowledgeOrganizer:
    def build(
        self,
        context: KnowledgeContext,
        relationships: Optional[list[Relationship]] = None,
    ) -> OrganizedKnowledge:
        relationship_payloads = [
            relationship.to_dict() for relationship in (relationships or [])
        ]

        return OrganizedKnowledge(
            primary_topic=context.primary_topic,
            description=context.description,
            characters=list(context.key_entities),
            claims=list(context.verified_claims),
            sources=list(context.supporting_sources),
            timeline=[],
            locations=[],
            relationships=relationship_payloads,
            metadata={},
        )


__all__ = ["KnowledgeOrganizer"]


