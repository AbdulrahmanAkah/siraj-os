from dataclasses import dataclass, field

from src.application.models.knowledge.important_typed_claim import ImportantTypedClaim


@dataclass
class PrioritizedKnowledge:
    primary_topic: str = ""
    description: str = ""
    characters: list[str] = field(default_factory=list)
    important_claims: list[ImportantTypedClaim] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    relationships: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "primary_topic": self.primary_topic,
            "description": self.description,
            "characters": self.characters,
            "important_claims": [claim.to_dict() for claim in self.important_claims],
            "sources": self.sources,
            "relationships": self.relationships,
            "metadata": self.metadata,
        }


__all__ = ["PrioritizedKnowledge"]


