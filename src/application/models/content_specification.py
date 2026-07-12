from dataclasses import dataclass


@dataclass
class ContentSpecification:
    platform: str = ""
    language: str = "ar"
    style: str = ""
    target_audience: str = ""
    duration_minutes: int = 0
    tone: str = ""
    include_citations: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "language": self.language,
            "style": self.style,
            "target_audience": self.target_audience,
            "duration_minutes": self.duration_minutes,
            "tone": self.tone,
            "include_citations": self.include_citations,
        }


__all__ = ["ContentSpecification"]


