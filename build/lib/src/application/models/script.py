from dataclasses import dataclass, field


@dataclass
class Script:
    title: str = ""
    introduction: str = ""
    body: str = ""
    conclusion: str = ""
    citations: list[str] = field(default_factory=list)
    language: str = "ar"
    metadata: dict[str, object] = field(default_factory=dict)
    narration: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "introduction": self.introduction,
            "body": self.body,
            "conclusion": self.conclusion,
            "citations": self.citations,
            "language": self.language,
            "metadata": self.metadata,
            "narration": self.narration,
        }


__all__ = ["Script"]
