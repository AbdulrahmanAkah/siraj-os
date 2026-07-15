from dataclasses import dataclass, field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT

@dataclass
class NarrativeArchitecturePolicy:
    policy_id: str
    roles: list[str] = field(default_factory=list)
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)

@dataclass
class NarrativeBeat:
    beat_id: str
    chapter_id: str
    role: str
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)

@dataclass
class NarrativeArchitecture:
    architecture_id: str
    documentary_plan_id: str
    beats: list[NarrativeBeat] = field(default_factory=list)
    beat_count: int = 0
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)
    validation_state: str = "VALID"
