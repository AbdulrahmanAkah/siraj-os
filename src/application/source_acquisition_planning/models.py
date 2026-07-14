from dataclasses import dataclass, field


@dataclass
class AcquisitionTarget:
    target_id: str
    query_id: str
    acquisition_method: str
    verification_requirement: str
    priority_level: str
    position: int


@dataclass
class AcquisitionBatch:
    batch_id: str
    discovery_bundle_id: str
    targets: list[AcquisitionTarget] = field(default_factory=list)


@dataclass
class SourceAcquisitionPlan:
    plan_id: str
    source_discovery_plan_id: str
    batches: list[AcquisitionBatch] = field(default_factory=list)
    target_count: int = 0


__all__ = ["AcquisitionBatch", "AcquisitionTarget", "SourceAcquisitionPlan"]
