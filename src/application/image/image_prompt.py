from dataclasses import dataclass


@dataclass
class ImagePrompt:
    scene_index: int
    prompt: str
    negative_prompt: str = ""

    def to_dict(self):
        return {
            "scene_index": self.scene_index,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
        }


__all__ = ["ImagePrompt"]


