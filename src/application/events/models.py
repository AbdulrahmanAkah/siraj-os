from dataclasses import dataclass, field


@dataclass
class HistoricalEvent:
    event_id: str
    title: str
    claim_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    year: int | None = None
    date: str | None = None


@dataclass
class HistoricalTimeline:
    timeline_id: str
    events: list[HistoricalEvent] = field(default_factory=list)
    ordered_event_ids: list[str] = field(default_factory=list)
    unplaced_event_ids: list[str] = field(default_factory=list)


__all__ = ["HistoricalEvent", "HistoricalTimeline"]
