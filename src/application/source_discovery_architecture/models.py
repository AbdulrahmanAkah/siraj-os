from dataclasses import dataclass, field


@dataclass
class DiscoveryQuery:
    query_id: str
    source_id: str
    discovery_channel: str
    query_strategy: str
    verification_level: str
    position: int


@dataclass
class DiscoveryBundle:
    bundle_id: str
    source_bundle_id: str
    queries: list[DiscoveryQuery] = field(default_factory=list)


@dataclass
class SourceDiscoveryPlan:
    plan_id: str
    visual_source_plan_id: str
    bundles: list[DiscoveryBundle] = field(default_factory=list)
    query_count: int = 0


__all__ = ["DiscoveryBundle", "DiscoveryQuery", "SourceDiscoveryPlan"]
