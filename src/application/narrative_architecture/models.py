from dataclasses import dataclass, field


@dataclass
class NarrativeBeat:
    beat_id: str
    title: str
    section_id: str
    event_ids: list[str] = field(default_factory=list)
    beat_type: str = ""
    importance: float = 0.0
    position: int = 0


@dataclass
class NarrativeArc:
    arc_id: str
    title: str
    beat_ids: list[str] = field(default_factory=list)
    importance: float = 0.0


@dataclass
class NarrativeArchitecture:
    architecture_id: str
    documentary_plan_id: str
    beats: list[NarrativeBeat] = field(default_factory=list)
    arcs: list[NarrativeArc] = field(default_factory=list)
    estimated_complexity: str = "LOW"


__all__ = ["NarrativeArc", "NarrativeArchitecture", "NarrativeBeat"]
