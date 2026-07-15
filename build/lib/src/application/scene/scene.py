from dataclasses import dataclass


@dataclass
class Scene:
    index: int
    title: str
    narration: str
    visual_description: str

    def to_dict(self):
        return {
            "index": self.index,
            "title": self.title,
            "narration": self.narration,
            "visual_description": self.visual_description,
        }


__all__ = ["Scene"]


