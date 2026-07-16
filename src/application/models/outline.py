from dataclasses import dataclass, field
from typing import List


@dataclass
class Outline:
    title: str = ""
    description: str = ""
    entities: List[str] = field(default_factory=list)
    claims: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "entities": self.entities,
            "claims": self.claims,
            "sources": self.sources,
        }


@dataclass
class DocumentaryOutline:
    title: str
    introduction: str
    sections: list[str]
    conclusion: str

    def to_dict(self):
        return {
            "title": self.title,
            "introduction": self.introduction,
            "sections": self.sections,
            "conclusion": self.conclusion,
        }


__all__ = [
    "Outline",
    "DocumentaryOutline",
]


