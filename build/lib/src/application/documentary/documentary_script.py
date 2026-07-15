from dataclasses import dataclass


@dataclass
class DocumentaryScript:
    topic: str
    text: str

    def to_dict(self):
        return {
            "topic": self.topic,
            "text": self.text,
        }


__all__ = ["DocumentaryScript"]


