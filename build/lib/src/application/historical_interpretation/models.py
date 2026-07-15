from dataclasses import dataclass, field


@dataclass
class HistoricalInterpretationPlan:
    plan_id: str
    validation_rules: list[str] = field(default_factory=list)


@dataclass
class InterpretationRecord:
    interpretation_id: str
    interpretation_text: str
    reasoning_chain_ids: list[str] = field(default_factory=list)
    narrative_record_ids: list[str] = field(default_factory=list)
    causal_relation_ids: list[str] = field(default_factory=list)
    temporal_relation_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    source_reference_ids: list[str] = field(default_factory=list)
    position: int = 0


@dataclass
class HistoricalInterpretationResult:
    result_id: str
    plan_id: str
    records: list[InterpretationRecord] = field(default_factory=list)
    record_count: int = 0
    validation_state: str = "VALID"


__all__ = [
    "HistoricalInterpretationPlan",
    "HistoricalInterpretationResult",
    "InterpretationRecord",
]
