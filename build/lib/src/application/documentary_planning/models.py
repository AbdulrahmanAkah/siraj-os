from dataclasses import dataclass, field


@dataclass
class DocumentarySection:
    section_id: str
    title: str
    event_ids: list[str] = field(default_factory=list)
    importance: float = 0.0
    estimated_duration: float = 0.0


@dataclass
class DocumentaryPlan:
    plan_id: str
    title: str
    sections: list[DocumentarySection] = field(default_factory=list)
    selected_event_ids: list[str] = field(default_factory=list)
    estimated_runtime: float = 0.0


__all__ = ["DocumentaryPlan", "DocumentarySection"]
