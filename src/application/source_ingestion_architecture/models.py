from dataclasses import dataclass, field


@dataclass
class IngestionUnit:
    unit_id: str
    acquisition_target_id: str
    normalization_strategy: str
    fingerprint_strategy: str
    deduplication_policy: str
    validation_level: str
    position: int


@dataclass
class IngestionBatch:
    batch_id: str
    acquisition_batch_id: str
    units: list[IngestionUnit] = field(default_factory=list)


@dataclass
class SourceIngestionPlan:
    plan_id: str
    source_acquisition_plan_id: str
    batches: list[IngestionBatch] = field(default_factory=list)
    unit_count: int = 0


__all__ = ["IngestionBatch", "IngestionUnit", "SourceIngestionPlan"]
