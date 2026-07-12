from dataclasses import dataclass, field
from typing import List


@dataclass
class ScriptStructure:
    title: str = ""
    introduction: List[str] = field(default_factory=list)
    main_points: List[str] = field(default_factory=list)
    conclusion: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "introduction": self.introduction,
            "main_points": self.main_points,
            "conclusion": self.conclusion,
            "sources": self.sources,
        }


__all__ = ["ScriptStructure"]


