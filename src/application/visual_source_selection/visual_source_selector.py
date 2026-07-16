from hashlib import sha256

from src.application.visual_asset_architecture.visual_asset_architect import (
    VisualAssetArchitect,
)

from .models import SourceBundle, VisualSource, VisualSourcePlan


class VisualSourceSelector:
    """Deterministically turns visual asset requirements into source categories."""

    _SOURCE_TYPES = {
        "HISTORICAL_PERSON": "ARCHIVE_PHOTOGRAPH",
        "HISTORICAL_LOCATION": "MUSEUM_COLLECTION",
        "HISTORICAL_OBJECT": "MUSEUM_COLLECTION",
        "DOCUMENT": "HISTORICAL_DOCUMENT",
        "MAP": "MAP_ARCHIVE",
        "TIMELINE_GRAPHIC": "TIMELINE_ASSET",
        "ARTWORK": "ART_RECONSTRUCTION",
    }
    _SOURCE_PRIORITIES = {
        "HISTORICAL_PERSON": "MANDATORY",
        "HISTORICAL_LOCATION": "MANDATORY",
        "HISTORICAL_OBJECT": "PREFERRED",
        "DOCUMENT": "MANDATORY",
        "MAP": "PREFERRED",
        "TIMELINE_GRAPHIC": "OPTIONAL",
        "ARTWORK": "OPTIONAL",
    }

    def __init__(self, visual_asset_architect):
        if not isinstance(visual_asset_architect, VisualAssetArchitect):
            raise TypeError(
                "VisualSourceSelector requires a VisualAssetArchitect"
            )
        self.visual_asset_architect = visual_asset_architect
        self._architectures_by_id = {}

    def build_visual_source_plan(self, visual_asset_architecture=None):
        visual_asset_architecture = self._architecture(visual_asset_architecture)
        self._architectures_by_id[visual_asset_architecture.architecture_id] = (
            visual_asset_architecture
        )
        bundles = self.generate_bundles(visual_asset_architecture)
        plan_key = "\x00".join(
            [visual_asset_architecture.architecture_id, *(bundle.bundle_id for bundle in bundles)]
        )
        return VisualSourcePlan(
            plan_id=(
                f"visual_source_plan_"
                f"{sha256(plan_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            visual_asset_architecture_id=visual_asset_architecture.architecture_id,
            bundles=bundles,
            source_count=sum(len(bundle.sources) for bundle in bundles),
        )

    def generate_bundles(self, visual_asset_architecture=None):
        visual_asset_architecture = self._architecture(visual_asset_architecture)
        bundles = []
        for group in visual_asset_architecture.asset_groups:
            bundle_key = "\x00".join(
                [visual_asset_architecture.architecture_id, group.group_id]
            )
            bundle_id = (
                f"source_bundle_"
                f"{sha256(bundle_key.encode('utf-8')).hexdigest()[:16]}"
            )
            bundles.append(
                SourceBundle(
                    bundle_id=bundle_id,
                    group_id=group.group_id,
                    sources=self.generate_sources(group),
                )
            )
        return bundles

    def generate_sources(self, asset_group_or_architecture=None):
        """Generate one ordered source-category requirement per visual asset."""
        if asset_group_or_architecture is None:
            architecture = self._architecture(None)
            groups = architecture.asset_groups
        elif hasattr(asset_group_or_architecture, "assets"):
            groups = [asset_group_or_architecture]
        else:
            groups = asset_group_or_architecture.asset_groups

        sources = []
        for group in groups:
            for position, asset in enumerate(group.assets):
                source_type = self._SOURCE_TYPES[asset.asset_type]
                source_priority = self._SOURCE_PRIORITIES[asset.asset_type]
                source_key = "\x00".join(
                    [asset.asset_id, source_type, source_priority]
                )
                sources.append(
                    VisualSource(
                        source_id=(
                            f"source_"
                            f"{sha256(source_key.encode('utf-8')).hexdigest()[:16]}"
                        ),
                        asset_id=asset.asset_id,
                        source_type=source_type,
                        source_priority=source_priority,
                        position=position,
                    )
                )
        return sources

    def assign_source_types(self, visual_asset_architecture=None):
        visual_asset_architecture = self._architecture(visual_asset_architecture)
        return {
            asset.asset_id: self._SOURCE_TYPES[asset.asset_type]
            for asset in self._assets(visual_asset_architecture)
        }

    def assign_priorities(self, visual_asset_architecture=None):
        visual_asset_architecture = self._architecture(visual_asset_architecture)
        return {
            asset.asset_id: self._SOURCE_PRIORITIES[asset.asset_type]
            for asset in self._assets(visual_asset_architecture)
        }

    def validate_source_plan(self, plan, visual_asset_architecture=None):
        if plan is None or not plan.bundles:
            return False
        visual_asset_architecture = self._validation_architecture(
            plan,
            visual_asset_architecture,
        )
        groups = visual_asset_architecture.asset_groups
        bundles = plan.bundles
        expected_assets = [
            asset
            for group in groups
            for asset in group.assets
        ]
        sources = [source for bundle in bundles for source in bundle.sources]
        expected_asset_ids = [asset.asset_id for asset in expected_assets]
        source_asset_ids = [source.asset_id for source in sources]
        bundle_ids = [bundle.bundle_id for bundle in bundles]
        bundle_group_ids = [bundle.group_id for bundle in bundles]
        group_ids = [group.group_id for group in groups]
        source_ids = [source.source_id for source in sources]

        if plan.visual_asset_architecture_id != visual_asset_architecture.architecture_id:
            return False
        if plan.source_count != len(sources):
            return False
        if len(bundle_ids) != len(set(bundle_ids)):
            return False
        if len(bundle_group_ids) != len(set(bundle_group_ids)):
            return False
        if len(source_ids) != len(set(source_ids)):
            return False
        if bundle_group_ids != group_ids:
            return False
        if set(bundle_group_ids) != set(group_ids):
            return False
        if source_asset_ids != expected_asset_ids:
            return False
        if len(source_asset_ids) != len(set(source_asset_ids)):
            return False
        if not any(source.source_priority == "MANDATORY" for source in sources):
            return False

        expected_types = self.assign_source_types(visual_asset_architecture)
        expected_priorities = self.assign_priorities(visual_asset_architecture)
        for bundle, group in zip(bundles, groups):
            if not bundle.sources:
                return False
            if bundle.group_id != group.group_id:
                return False
            if [source.position for source in bundle.sources] != list(
                range(len(bundle.sources))
            ):
                return False
            if bundle.sources != sorted(
                bundle.sources,
                key=lambda item: (item.position, item.source_id),
            ):
                return False
            if [source.asset_id for source in bundle.sources] != [
                asset.asset_id for asset in group.assets
            ]:
                return False
            if any(
                source.source_type != expected_types[source.asset_id]
                or source.source_priority != expected_priorities[source.asset_id]
                or not isinstance(source.position, int)
                or isinstance(source.position, bool)
                for source in bundle.sources
            ):
                return False
        return True

    def _architecture(self, visual_asset_architecture):
        return (
            self.visual_asset_architect.build_visual_asset_architecture()
            if visual_asset_architecture is None
            else visual_asset_architecture
        )

    def _validation_architecture(self, plan, visual_asset_architecture):
        if visual_asset_architecture is not None:
            return visual_asset_architecture
        return self._architectures_by_id.get(
            plan.visual_asset_architecture_id
        ) or self._architecture(None)

    @staticmethod
    def _assets(visual_asset_architecture):
        return [
            asset
            for group in visual_asset_architecture.asset_groups
            for asset in group.assets
        ]


__all__ = ["VisualSourceSelector"]
