from hashlib import sha256

from src.application.source_discovery_architecture.source_discovery_architect import (
    SourceDiscoveryArchitect,
)

from .models import AcquisitionBatch, AcquisitionTarget, SourceAcquisitionPlan


class SourceAcquisitionPlanner:
    """Deterministically plans future acquisition work without acquiring sources."""

    _ACQUISITION_METHODS = {
        "PUBLIC_ARCHIVE": "ARCHIVE_REQUEST",
        "MUSEUM_CATALOG": "CATALOG_LOOKUP",
        "LIBRARY_CATALOG": "DOCUMENT_RETRIEVAL",
        "MAP_REPOSITORY": "MAP_RETRIEVAL",
        "ACADEMIC_INDEX": "ACADEMIC_LOOKUP",
        "ART_COLLECTION": "COLLECTION_REVIEW",
        "INTERNAL_ASSET_LIBRARY": "INTERNAL_FETCH",
    }
    _VERIFICATION_REQUIREMENTS = {
        "PUBLIC_ARCHIVE": "STRICT_VERIFICATION",
        "MUSEUM_CATALOG": "STRICT_VERIFICATION",
        "LIBRARY_CATALOG": "STRICT_VERIFICATION",
        "MAP_REPOSITORY": "STANDARD_VERIFICATION",
        "ACADEMIC_INDEX": "STRICT_VERIFICATION",
        "ART_COLLECTION": "STANDARD_VERIFICATION",
        "INTERNAL_ASSET_LIBRARY": "BASIC_VERIFICATION",
    }
    _PRIORITY_LEVELS = {
        "PUBLIC_ARCHIVE": "CRITICAL",
        "MUSEUM_CATALOG": "HIGH",
        "LIBRARY_CATALOG": "HIGH",
        "MAP_REPOSITORY": "MEDIUM",
        "ACADEMIC_INDEX": "HIGH",
        "ART_COLLECTION": "LOW",
        "INTERNAL_ASSET_LIBRARY": "LOW",
    }

    def __init__(self, source_discovery_architect):
        if not isinstance(source_discovery_architect, SourceDiscoveryArchitect):
            raise TypeError(
                "SourceAcquisitionPlanner requires a SourceDiscoveryArchitect"
            )
        self.source_discovery_architect = source_discovery_architect
        self._plans_by_id = {}

    def build_source_acquisition_plan(self, source_discovery_plan=None):
        source_discovery_plan = self._plan(source_discovery_plan)
        self._plans_by_id[source_discovery_plan.plan_id] = source_discovery_plan
        batches = self.generate_batches(source_discovery_plan)
        plan_key = "\x00".join(
            [source_discovery_plan.plan_id, *(batch.batch_id for batch in batches)]
        )
        return SourceAcquisitionPlan(
            plan_id=(
                f"source_acquisition_plan_"
                f"{sha256(plan_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            source_discovery_plan_id=source_discovery_plan.plan_id,
            batches=batches,
            target_count=sum(len(batch.targets) for batch in batches),
        )

    def generate_batches(self, source_discovery_plan=None):
        source_discovery_plan = self._plan(source_discovery_plan)
        batches = []
        for discovery_bundle in source_discovery_plan.bundles:
            batch_key = "\x00".join(
                [source_discovery_plan.plan_id, discovery_bundle.bundle_id]
            )
            batch_id = (
                f"acquisition_batch_"
                f"{sha256(batch_key.encode('utf-8')).hexdigest()[:16]}"
            )
            batches.append(
                AcquisitionBatch(
                    batch_id=batch_id,
                    discovery_bundle_id=discovery_bundle.bundle_id,
                    targets=self.generate_targets(discovery_bundle),
                )
            )
        return batches

    def generate_targets(self, discovery_bundle_or_plan=None):
        """Generate one deterministic acquisition target per discovery query."""
        if discovery_bundle_or_plan is None:
            source_discovery_plan = self._plan(None)
            discovery_bundles = source_discovery_plan.bundles
        elif hasattr(discovery_bundle_or_plan, "queries"):
            discovery_bundles = [discovery_bundle_or_plan]
        else:
            discovery_bundles = discovery_bundle_or_plan.bundles

        targets = []
        for discovery_bundle in discovery_bundles:
            for position, query in enumerate(discovery_bundle.queries):
                acquisition_method = self._ACQUISITION_METHODS[
                    query.discovery_channel
                ]
                verification_requirement = self._VERIFICATION_REQUIREMENTS[
                    query.discovery_channel
                ]
                priority_level = self._PRIORITY_LEVELS[query.discovery_channel]
                target_key = "\x00".join(
                    [
                        query.query_id,
                        acquisition_method,
                        verification_requirement,
                        priority_level,
                    ]
                )
                targets.append(
                    AcquisitionTarget(
                        target_id=(
                            f"acquisition_target_"
                            f"{sha256(target_key.encode('utf-8')).hexdigest()[:16]}"
                        ),
                        query_id=query.query_id,
                        acquisition_method=acquisition_method,
                        verification_requirement=verification_requirement,
                        priority_level=priority_level,
                        position=position,
                    )
                )
        return targets

    def assign_acquisition_methods(self, source_discovery_plan=None):
        source_discovery_plan = self._plan(source_discovery_plan)
        return {
            query.query_id: self._ACQUISITION_METHODS[query.discovery_channel]
            for query in self._queries(source_discovery_plan)
        }

    def assign_verification_requirements(self, source_discovery_plan=None):
        source_discovery_plan = self._plan(source_discovery_plan)
        return {
            query.query_id: self._VERIFICATION_REQUIREMENTS[query.discovery_channel]
            for query in self._queries(source_discovery_plan)
        }

    def assign_priorities(self, source_discovery_plan=None):
        source_discovery_plan = self._plan(source_discovery_plan)
        return {
            query.query_id: self._PRIORITY_LEVELS[query.discovery_channel]
            for query in self._queries(source_discovery_plan)
        }

    def validate_acquisition_plan(self, plan, source_discovery_plan=None):
        if plan is None or not plan.batches:
            return False
        source_discovery_plan = self._validation_plan(plan, source_discovery_plan)
        discovery_bundles = source_discovery_plan.bundles
        batches = plan.batches
        expected_queries = [
            query
            for discovery_bundle in discovery_bundles
            for query in discovery_bundle.queries
        ]
        targets = [target for batch in batches for target in batch.targets]
        expected_query_ids = [query.query_id for query in expected_queries]
        target_query_ids = [target.query_id for target in targets]
        batch_ids = [batch.batch_id for batch in batches]
        batch_discovery_bundle_ids = [
            batch.discovery_bundle_id for batch in batches
        ]
        discovery_bundle_ids = [
            discovery_bundle.bundle_id for discovery_bundle in discovery_bundles
        ]
        target_ids = [target.target_id for target in targets]

        if plan.source_discovery_plan_id != source_discovery_plan.plan_id:
            return False
        if plan.target_count != len(targets):
            return False
        if len(batch_ids) != len(set(batch_ids)):
            return False
        if len(batch_discovery_bundle_ids) != len(set(batch_discovery_bundle_ids)):
            return False
        if len(target_ids) != len(set(target_ids)):
            return False
        if batch_discovery_bundle_ids != discovery_bundle_ids:
            return False
        if set(batch_discovery_bundle_ids) != set(discovery_bundle_ids):
            return False
        if target_query_ids != expected_query_ids:
            return False
        if len(target_query_ids) != len(set(target_query_ids)):
            return False
        if not any(target.priority_level == "CRITICAL" for target in targets):
            return False

        expected_methods = self.assign_acquisition_methods(source_discovery_plan)
        expected_verification = self.assign_verification_requirements(
            source_discovery_plan
        )
        expected_priorities = self.assign_priorities(source_discovery_plan)
        for batch, discovery_bundle in zip(batches, discovery_bundles):
            if not batch.targets:
                return False
            if batch.discovery_bundle_id != discovery_bundle.bundle_id:
                return False
            if [target.position for target in batch.targets] != list(
                range(len(batch.targets))
            ):
                return False
            if batch.targets != sorted(
                batch.targets,
                key=lambda item: (item.position, item.target_id),
            ):
                return False
            if [target.query_id for target in batch.targets] != [
                query.query_id for query in discovery_bundle.queries
            ]:
                return False
            if any(
                target.acquisition_method != expected_methods[target.query_id]
                or target.verification_requirement
                != expected_verification[target.query_id]
                or target.priority_level != expected_priorities[target.query_id]
                or target.acquisition_method not in self._ACQUISITION_METHODS.values()
                or target.verification_requirement
                not in self._VERIFICATION_REQUIREMENTS.values()
                or target.priority_level not in self._PRIORITY_LEVELS.values()
                or not isinstance(target.position, int)
                or isinstance(target.position, bool)
                for target in batch.targets
            ):
                return False
        return True

    def _plan(self, source_discovery_plan):
        return (
            self.source_discovery_architect.build_source_discovery_plan()
            if source_discovery_plan is None
            else source_discovery_plan
        )

    def _validation_plan(self, plan, source_discovery_plan):
        if source_discovery_plan is not None:
            return source_discovery_plan
        return self._plans_by_id.get(
            plan.source_discovery_plan_id
        ) or self._plan(None)

    @staticmethod
    def _queries(source_discovery_plan):
        return [
            query
            for discovery_bundle in source_discovery_plan.bundles
            for query in discovery_bundle.queries
        ]


__all__ = ["SourceAcquisitionPlanner"]
