from dataclasses import dataclass, field


@dataclass
class ScenePlan:
    index: int
    title: str
    objective: str
    key_points: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "index": self.index,
            "title": self.title,
            "objective": self.objective,
            "key_points": self.key_points,
        }


__all__ = ["ScenePlan"]


