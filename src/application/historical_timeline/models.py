from dataclasses import dataclass, field


@dataclass
class TimelineCandidate:
    candidate_id: str
    event_id: str
    event_type: str
    event_title: str
    event_date: str | None
    source_claim_ids: list[str] = field(default_factory=list)
    source_entity_ids: list[str] = field(default_factory=list)


@dataclass
class TimelinePlan:
    plan_id: str
    allowed_event_types: list[str] = field(default_factory=list)
    include_undated_events: bool = True
    validation_level: str = "STANDARD"


@dataclass
class TimelineEntry:
    entry_id: str
    event_id: str
    event_type: str
    event_title: str
    event_date: str | None
    source_claim_ids: list[str] = field(default_factory=list)
    source_entity_ids: list[str] = field(default_factory=list)


@dataclass
class HistoricalTimeline:
    timeline_id: str
    plan_id: str
    entries: list[TimelineEntry] = field(default_factory=list)
    entry_count: int = 0


@dataclass
class TimelineBuildResult:
    result_id: str
    timeline: HistoricalTimeline
    validation_state: str = "VALID"
    entry_count: int = 0


__all__ = [
    "HistoricalTimeline",
    "TimelineBuildResult",
    "TimelineCandidate",
    "TimelineEntry",
    "TimelinePlan",
]
