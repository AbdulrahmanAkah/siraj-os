from dataclasses import dataclass, field


@dataclass
class OrganizedKnowledge:
    primary_topic: str = ""
    description: str = ""
    characters: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    relationships: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "primary_topic": self.primary_topic,
            "description": self.description,
            "characters": self.characters,
            "claims": self.claims,
            "sources": self.sources,
            "timeline": self.timeline,
            "locations": self.locations,
            "relationships": self.relationships,
            "metadata": self.metadata,
        }


__all__ = ["OrganizedKnowledge"]
