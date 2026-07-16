from dataclasses import dataclass, field


@dataclass
class VisualAsset:
    asset_id: str
    frame_id: str
    asset_type: str
    asset_role: str
    priority: str
    position: int


@dataclass
class AssetGroup:
    group_id: str
    sequence_id: str
    assets: list[VisualAsset] = field(default_factory=list)


@dataclass
class VisualAssetArchitecture:
    architecture_id: str
    storyboard_architecture_id: str
    asset_groups: list[AssetGroup] = field(default_factory=list)
    asset_count: int = 0


__all__ = ["AssetGroup", "VisualAsset", "VisualAssetArchitecture"]
