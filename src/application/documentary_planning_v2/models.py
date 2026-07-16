from dataclasses import dataclass, field

from src.application.documentary_intelligence import CANONICAL_CREATED_AT


@dataclass
class DocumentaryPlanningPolicy:
    policy_id: str
    allowed_chapter_roles: list[str] = field(default_factory=list)
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class DocumentaryChapter:
    chapter_id: str
    title: str
    chapter_role: str
    event_ids: list[str] = field(default_factory=list)
    interpretation_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class DocumentaryPlan:
    plan_id: str
    title: str
    subject: str
    scope: str
    time_range: tuple[str | None, str | None]
    major_chapters: list[DocumentaryChapter] = field(default_factory=list)
    chapter_ordering: list[str] = field(default_factory=list)
    evidence_coverage: list[str] = field(default_factory=list)
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)
    validation_state: str = "VALID"


__all__ = ["DocumentaryChapter", "DocumentaryPlan", "DocumentaryPlanningPolicy"]
