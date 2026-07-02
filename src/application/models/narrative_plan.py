from dataclasses import dataclass, field


@dataclass
class NarrativePlan:
    title: str = ""
    hook: list[str] = field(default_factory=list)
    background: list[str] = field(default_factory=list)
    main_story: list[str] = field(default_factory=list)
    conclusion: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "hook": self.hook,
            "background": self.background,
            "main_story": self.main_story,
            "conclusion": self.conclusion,
            "sources": self.sources,
            "metadata": self.metadata,
        }


__all__ = ["NarrativePlan"]
