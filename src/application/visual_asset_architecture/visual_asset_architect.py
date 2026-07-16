from hashlib import sha256

from src.application.storyboard_architecture.storyboard_architect import (
    StoryboardArchitect,
)

from .models import AssetGroup, VisualAsset, VisualAssetArchitecture


class VisualAssetArchitect:
    """Deterministically turns storyboard architecture into asset requirements."""

    _ASSET_TYPES = {
        "ESTABLISHING": "HISTORICAL_LOCATION",
        "CONTEXTUAL": "MAP",
        "DETAIL": "HISTORICAL_OBJECT",
        "REVEAL": "DOCUMENT",
        "CLIMAX": "HISTORICAL_PERSON",
        "TRANSITION": "TIMELINE_GRAPHIC",
        "CLOSING": "ARTWORK",
    }
    _ASSET_ROLES = {
        "ESTABLISHING": "PRIMARY",
        "CONTEXTUAL": "CONTEXT",
        "DETAIL": "SUPPORTING",
        "REVEAL": "EVIDENCE",
        "CLIMAX": "PRIMARY",
        "TRANSITION": "TRANSITION",
        "CLOSING": "CONTEXT",
    }
    _PRIORITIES = {
        "ESTABLISHING": "CRITICAL",
        "CONTEXTUAL": "HIGH",
        "DETAIL": "MEDIUM",
        "REVEAL": "HIGH",
        "CLIMAX": "CRITICAL",
        "TRANSITION": "MEDIUM",
        "CLOSING": "LOW",
    }

    def __init__(self, storyboard_architect):
        if not isinstance(storyboard_architect, StoryboardArchitect):
            raise TypeError("VisualAssetArchitect requires a StoryboardArchitect")
        self.storyboard_architect = storyboard_architect
        self._architectures_by_id = {}

    def build_visual_asset_architecture(self, storyboard_architecture=None):
        storyboard_architecture = self._architecture(storyboard_architecture)
        self._architectures_by_id[storyboard_architecture.architecture_id] = (
            storyboard_architecture
        )
        asset_groups = self.generate_asset_groups(storyboard_architecture)
        architecture_key = "\x00".join(
            [
                storyboard_architecture.architecture_id,
                *(group.group_id for group in asset_groups),
            ]
        )
        return VisualAssetArchitecture(
            architecture_id=(
                f"visual_asset_architecture_"
                f"{sha256(architecture_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            storyboard_architecture_id=storyboard_architecture.architecture_id,
            asset_groups=asset_groups,
            asset_count=sum(len(group.assets) for group in asset_groups),
        )

    def generate_asset_groups(self, storyboard_architecture=None):
        storyboard_architecture = self._architecture(storyboard_architecture)
        groups = []
        for sequence in storyboard_architecture.sequences:
            group_key = "\x00".join(
                [storyboard_architecture.architecture_id, sequence.sequence_id]
            )
            group_id = (
                f"asset_group_"
                f"{sha256(group_key.encode('utf-8')).hexdigest()[:16]}"
            )
            groups.append(
                AssetGroup(
                    group_id=group_id,
                    sequence_id=sequence.sequence_id,
                    assets=self.generate_assets(sequence),
                )
            )
        return groups

    def generate_assets(self, storyboard_sequence_or_architecture=None):
        """Generate one ordered asset requirement for each storyboard frame."""
        if storyboard_sequence_or_architecture is None:
            storyboard_architecture = self._architecture(None)
            sequences = storyboard_architecture.sequences
        elif hasattr(storyboard_sequence_or_architecture, "frames"):
            sequences = [storyboard_sequence_or_architecture]
        else:
            sequences = storyboard_sequence_or_architecture.sequences

        assets = []
        for sequence in sequences:
            for position, frame in enumerate(sequence.frames):
                asset_type = self._ASSET_TYPES[frame.frame_type]
                asset_role = self._ASSET_ROLES[frame.frame_type]
                priority = self._PRIORITIES[frame.frame_type]
                asset_key = "\x00".join(
                    [frame.frame_id, asset_type, asset_role, priority]
                )
                assets.append(
                    VisualAsset(
                        asset_id=(
                            f"asset_"
                            f"{sha256(asset_key.encode('utf-8')).hexdigest()[:16]}"
                        ),
                        frame_id=frame.frame_id,
                        asset_type=asset_type,
                        asset_role=asset_role,
                        priority=priority,
                        position=position,
                    )
                )
        return assets

    def assign_asset_types(self, storyboard_architecture=None):
        storyboard_architecture = self._architecture(storyboard_architecture)
        return {
            frame.frame_id: self._ASSET_TYPES[frame.frame_type]
            for frame in self._frames(storyboard_architecture)
        }

    def assign_asset_roles(self, storyboard_architecture=None):
        storyboard_architecture = self._architecture(storyboard_architecture)
        return {
            frame.frame_id: self._ASSET_ROLES[frame.frame_type]
            for frame in self._frames(storyboard_architecture)
        }

    def assign_priorities(self, storyboard_architecture=None):
        storyboard_architecture = self._architecture(storyboard_architecture)
        return {
            frame.frame_id: self._PRIORITIES[frame.frame_type]
            for frame in self._frames(storyboard_architecture)
        }

    def validate_architecture(self, architecture, storyboard_architecture=None):
        if architecture is None or not architecture.asset_groups:
            return False
        storyboard_architecture = self._validation_architecture(
            architecture,
            storyboard_architecture,
        )
        sequences = storyboard_architecture.sequences
        groups = architecture.asset_groups
        expected_frames = [
            frame
            for sequence in sequences
            for frame in sequence.frames
        ]
        assets = [asset for group in groups for asset in group.assets]
        expected_frame_ids = [frame.frame_id for frame in expected_frames]
        asset_frame_ids = [asset.frame_id for asset in assets]
        group_ids = [group.group_id for group in groups]
        group_sequence_ids = [group.sequence_id for group in groups]
        sequence_ids = [sequence.sequence_id for sequence in sequences]
        asset_ids = [asset.asset_id for asset in assets]

        if architecture.storyboard_architecture_id != storyboard_architecture.architecture_id:
            return False
        if architecture.asset_count != len(assets):
            return False
        if len(group_ids) != len(set(group_ids)):
            return False
        if len(group_sequence_ids) != len(set(group_sequence_ids)):
            return False
        if len(asset_ids) != len(set(asset_ids)):
            return False
        if group_sequence_ids != sequence_ids:
            return False
        if set(group_sequence_ids) != set(sequence_ids):
            return False
        if asset_frame_ids != expected_frame_ids:
            return False
        if len(asset_frame_ids) != len(set(asset_frame_ids)):
            return False
        if not any(asset.priority == "CRITICAL" for asset in assets):
            return False
        if not any(asset.asset_role == "PRIMARY" for asset in assets):
            return False

        expected_types = self.assign_asset_types(storyboard_architecture)
        expected_roles = self.assign_asset_roles(storyboard_architecture)
        expected_priorities = self.assign_priorities(storyboard_architecture)
        for group, sequence in zip(groups, sequences):
            if not group.assets:
                return False
            if group.sequence_id != sequence.sequence_id:
                return False
            if [asset.position for asset in group.assets] != list(
                range(len(group.assets))
            ):
                return False
            if group.assets != sorted(
                group.assets,
                key=lambda item: (item.position, item.asset_id),
            ):
                return False
            if [asset.frame_id for asset in group.assets] != [
                frame.frame_id for frame in sequence.frames
            ]:
                return False
            if any(
                asset.asset_type != expected_types[asset.frame_id]
                or asset.asset_role != expected_roles[asset.frame_id]
                or asset.priority != expected_priorities[asset.frame_id]
                or not isinstance(asset.position, int)
                or isinstance(asset.position, bool)
                for asset in group.assets
            ):
                return False
        return True

    def _architecture(self, storyboard_architecture):
        return (
            self.storyboard_architect.build_storyboard_architecture()
            if storyboard_architecture is None
            else storyboard_architecture
        )

    def _validation_architecture(self, architecture, storyboard_architecture):
        if storyboard_architecture is not None:
            return storyboard_architecture
        return self._architectures_by_id.get(
            architecture.storyboard_architecture_id
        ) or self._architecture(None)

    @staticmethod
    def _frames(storyboard_architecture):
        return [
            frame
            for sequence in storyboard_architecture.sequences
            for frame in sequence.frames
        ]


__all__ = ["VisualAssetArchitect"]
