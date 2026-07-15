from dataclasses import dataclass, field


@dataclass
class KnowledgeContext:
    primary_topic: str = ""
    description: str = ""
    key_entities: list[str] = field(default_factory=list)
    verified_claims: list[str] = field(default_factory=list)
    supporting_sources: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "primary_topic": self.primary_topic,
            "description": self.description,
            "key_entities": self.key_entities,
            "verified_claims": self.verified_claims,
            "supporting_sources": self.supporting_sources,
            "metadata": self.metadata,
        }


__all__ = ["KnowledgeContext"]


