from hashlib import sha256

from src.application.visual_source_selection.visual_source_selector import (
    VisualSourceSelector,
)

from .models import DiscoveryBundle, DiscoveryQuery, SourceDiscoveryPlan


class SourceDiscoveryArchitect:
    """Deterministically plans future discovery channels without retrieving sources."""

    _DISCOVERY_CHANNELS = {
        "ARCHIVE_PHOTOGRAPH": "PUBLIC_ARCHIVE",
        "MUSEUM_COLLECTION": "MUSEUM_CATALOG",
        "HISTORICAL_DOCUMENT": "LIBRARY_CATALOG",
        "MAP_ARCHIVE": "MAP_REPOSITORY",
        "ACADEMIC_SOURCE": "ACADEMIC_INDEX",
        "ART_RECONSTRUCTION": "ART_COLLECTION",
        "TIMELINE_ASSET": "INTERNAL_ASSET_LIBRARY",
    }
    _QUERY_STRATEGIES = {
        "ARCHIVE_PHOTOGRAPH": "ENTITY_AND_DATE",
        "MUSEUM_COLLECTION": "ENTITY_AND_LOCATION",
        "HISTORICAL_DOCUMENT": "DOCUMENT_TITLE",
        "MAP_ARCHIVE": "ENTITY_AND_LOCATION",
        "ACADEMIC_SOURCE": "SUBJECT_SEARCH",
        "ART_RECONSTRUCTION": "COLLECTION_BROWSE",
        "TIMELINE_ASSET": "METADATA_FILTER",
    }
    _VERIFICATION_LEVELS = {
        "ARCHIVE_PHOTOGRAPH": "STRICT",
        "MUSEUM_COLLECTION": "STRICT",
        "HISTORICAL_DOCUMENT": "STRICT",
        "MAP_ARCHIVE": "STANDARD",
        "ACADEMIC_SOURCE": "STRICT",
        "ART_RECONSTRUCTION": "STANDARD",
        "TIMELINE_ASSET": "BASIC",
    }

    def __init__(self, visual_source_selector):
        if not isinstance(visual_source_selector, VisualSourceSelector):
            raise TypeError(
                "SourceDiscoveryArchitect requires a VisualSourceSelector"
            )
        self.visual_source_selector = visual_source_selector
        self._plans_by_id = {}

    def build_source_discovery_plan(self, visual_source_plan=None):
        visual_source_plan = self._plan(visual_source_plan)
        self._plans_by_id[visual_source_plan.plan_id] = visual_source_plan
        bundles = self.generate_discovery_bundles(visual_source_plan)
        plan_key = "\x00".join(
            [visual_source_plan.plan_id, *(bundle.bundle_id for bundle in bundles)]
        )
        return SourceDiscoveryPlan(
            plan_id=(
                f"source_discovery_plan_"
                f"{sha256(plan_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            visual_source_plan_id=visual_source_plan.plan_id,
            bundles=bundles,
            query_count=sum(len(bundle.queries) for bundle in bundles),
        )

    def generate_discovery_bundles(self, visual_source_plan=None):
        visual_source_plan = self._plan(visual_source_plan)
        bundles = []
        for source_bundle in visual_source_plan.bundles:
            bundle_key = "\x00".join(
                [visual_source_plan.plan_id, source_bundle.bundle_id]
            )
            bundle_id = (
                f"discovery_bundle_"
                f"{sha256(bundle_key.encode('utf-8')).hexdigest()[:16]}"
            )
            bundles.append(
                DiscoveryBundle(
                    bundle_id=bundle_id,
                    source_bundle_id=source_bundle.bundle_id,
                    queries=self.generate_queries(source_bundle),
                )
            )
        return bundles

    def generate_queries(self, source_bundle_or_plan=None):
        """Generate one deterministic discovery specification per visual source."""
        if source_bundle_or_plan is None:
            visual_source_plan = self._plan(None)
            source_bundles = visual_source_plan.bundles
        elif hasattr(source_bundle_or_plan, "sources"):
            source_bundles = [source_bundle_or_plan]
        else:
            source_bundles = source_bundle_or_plan.bundles

        queries = []
        for source_bundle in source_bundles:
            for position, source in enumerate(source_bundle.sources):
                discovery_channel = self._DISCOVERY_CHANNELS[source.source_type]
                query_strategy = self._QUERY_STRATEGIES[source.source_type]
                verification_level = self._VERIFICATION_LEVELS[source.source_type]
                query_key = "\x00".join(
                    [
                        source.source_id,
                        discovery_channel,
                        query_strategy,
                        verification_level,
                    ]
                )
                queries.append(
                    DiscoveryQuery(
                        query_id=(
                            f"discovery_query_"
                            f"{sha256(query_key.encode('utf-8')).hexdigest()[:16]}"
                        ),
                        source_id=source.source_id,
                        discovery_channel=discovery_channel,
                        query_strategy=query_strategy,
                        verification_level=verification_level,
                        position=position,
                    )
                )
        return queries

    def assign_discovery_channels(self, visual_source_plan=None):
        visual_source_plan = self._plan(visual_source_plan)
        return {
            source.source_id: self._DISCOVERY_CHANNELS[source.source_type]
            for source in self._sources(visual_source_plan)
        }

    def assign_query_strategies(self, visual_source_plan=None):
        visual_source_plan = self._plan(visual_source_plan)
        return {
            source.source_id: self._QUERY_STRATEGIES[source.source_type]
            for source in self._sources(visual_source_plan)
        }

    def assign_verification_levels(self, visual_source_plan=None):
        visual_source_plan = self._plan(visual_source_plan)
        return {
            source.source_id: self._VERIFICATION_LEVELS[source.source_type]
            for source in self._sources(visual_source_plan)
        }

    def validate_discovery_plan(self, plan, visual_source_plan=None):
        if plan is None or not plan.bundles:
            return False
        visual_source_plan = self._validation_plan(plan, visual_source_plan)
        source_bundles = visual_source_plan.bundles
        bundles = plan.bundles
        expected_sources = [
            source
            for source_bundle in source_bundles
            for source in source_bundle.sources
        ]
        queries = [query for bundle in bundles for query in bundle.queries]
        expected_source_ids = [source.source_id for source in expected_sources]
        query_source_ids = [query.source_id for query in queries]
        bundle_ids = [bundle.bundle_id for bundle in bundles]
        bundle_source_bundle_ids = [bundle.source_bundle_id for bundle in bundles]
        source_bundle_ids = [source_bundle.bundle_id for source_bundle in source_bundles]
        query_ids = [query.query_id for query in queries]

        if plan.visual_source_plan_id != visual_source_plan.plan_id:
            return False
        if plan.query_count != len(queries):
            return False
        if len(bundle_ids) != len(set(bundle_ids)):
            return False
        if len(bundle_source_bundle_ids) != len(set(bundle_source_bundle_ids)):
            return False
        if len(query_ids) != len(set(query_ids)):
            return False
        if bundle_source_bundle_ids != source_bundle_ids:
            return False
        if set(bundle_source_bundle_ids) != set(source_bundle_ids):
            return False
        if query_source_ids != expected_source_ids:
            return False
        if len(query_source_ids) != len(set(query_source_ids)):
            return False
        if not any(query.verification_level == "STRICT" for query in queries):
            return False

        expected_channels = self.assign_discovery_channels(visual_source_plan)
        expected_strategies = self.assign_query_strategies(visual_source_plan)
        expected_verification = self.assign_verification_levels(visual_source_plan)
        for bundle, source_bundle in zip(bundles, source_bundles):
            if not bundle.queries:
                return False
            if bundle.source_bundle_id != source_bundle.bundle_id:
                return False
            if [query.position for query in bundle.queries] != list(
                range(len(bundle.queries))
            ):
                return False
            if bundle.queries != sorted(
                bundle.queries,
                key=lambda item: (item.position, item.query_id),
            ):
                return False
            if [query.source_id for query in bundle.queries] != [
                source.source_id for source in source_bundle.sources
            ]:
                return False
            if any(
                query.discovery_channel != expected_channels[query.source_id]
                or query.query_strategy != expected_strategies[query.source_id]
                or query.verification_level != expected_verification[query.source_id]
                or query.discovery_channel not in self._DISCOVERY_CHANNELS.values()
                or query.query_strategy not in self._QUERY_STRATEGIES.values()
                or query.verification_level not in self._VERIFICATION_LEVELS.values()
                or not isinstance(query.position, int)
                or isinstance(query.position, bool)
                for query in bundle.queries
            ):
                return False
        return True

    def _plan(self, visual_source_plan):
        return (
            self.visual_source_selector.build_visual_source_plan()
            if visual_source_plan is None
            else visual_source_plan
        )

    def _validation_plan(self, plan, visual_source_plan):
        if visual_source_plan is not None:
            return visual_source_plan
        return self._plans_by_id.get(
            plan.visual_source_plan_id
        ) or self._plan(None)

    @staticmethod
    def _sources(visual_source_plan):
        return [
            source
            for source_bundle in visual_source_plan.bundles
            for source in source_bundle.sources
        ]


__all__ = ["SourceDiscoveryArchitect"]
