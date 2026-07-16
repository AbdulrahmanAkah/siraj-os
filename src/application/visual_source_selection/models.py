from dataclasses import dataclass, field


@dataclass
class VisualSource:
    source_id: str
    asset_id: str
    source_type: str
    source_priority: str
    position: int


@dataclass
class SourceBundle:
    bundle_id: str
    group_id: str
    sources: list[VisualSource] = field(default_factory=list)


@dataclass
class VisualSourcePlan:
    plan_id: str
    visual_asset_architecture_id: str
    bundles: list[SourceBundle] = field(default_factory=list)
    source_count: int = 0


__all__ = ["SourceBundle", "VisualSource", "VisualSourcePlan"]
