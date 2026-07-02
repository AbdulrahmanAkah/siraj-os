from dataclasses import dataclass, field
from typing import List


@dataclass
class Outline:
    title: str = ""
    description: str = ""
    entities: List[str] = field(default_factory=list)
    claims: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "description": self.description,
            "entities": self.entities,
            "claims": self.claims,
            "sources": self.sources,
        }


__all__ = ["Outline"]
