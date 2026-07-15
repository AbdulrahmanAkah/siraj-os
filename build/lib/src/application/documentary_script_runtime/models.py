from dataclasses import dataclass, field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT

@dataclass
class DocumentaryScriptPolicy:
    policy_id: str
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)
@dataclass
class ScriptParagraph:
    paragraph_id: str
    text: str
    evidence_ids: list[str] = field(default_factory=list)
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)
@dataclass
class ScriptSection:
    section_id: str
    beat_id: str
    role: str
    paragraphs: list[ScriptParagraph] = field(default_factory=list)
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)
@dataclass
class DocumentaryScript:
    script_id: str
    narrative_architecture_id: str
    sections: list[ScriptSection] = field(default_factory=list)
    section_count: int = 0
    created_at: str = CANONICAL_CREATED_AT
    position: int = 0
    trace_metadata: dict[str, list[str]] = field(default_factory=dict)
    validation_state: str = "VALID"
