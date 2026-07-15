from hashlib import sha256

from src.application.source_acquisition_planning.source_acquisition_planner import (
    SourceAcquisitionPlanner,
)

from .models import IngestionBatch, IngestionUnit, SourceIngestionPlan


class SourceIngestionArchitect:
    """Deterministically plans future ingestion preparation without execution."""

    _NORMALIZATION_STRATEGIES = {
        "ARCHIVE_REQUEST": "ARCHIVE_NORMALIZATION",
        "CATALOG_LOOKUP": "METADATA_NORMALIZATION",
        "DOCUMENT_RETRIEVAL": "DOCUMENT_NORMALIZATION",
        "MAP_RETRIEVAL": "MAP_NORMALIZATION",
        "ACADEMIC_LOOKUP": "DOCUMENT_NORMALIZATION",
        "COLLECTION_REVIEW": "IMAGE_NORMALIZATION",
        "INTERNAL_FETCH": "METADATA_NORMALIZATION",
    }
    _FINGERPRINT_STRATEGIES = {
        "ARCHIVE_REQUEST": "SHA256_FINGERPRINT",
        "CATALOG_LOOKUP": "METADATA_FINGERPRINT",
        "DOCUMENT_RETRIEVAL": "SHA256_FINGERPRINT",
        "MAP_RETRIEVAL": "PERCEPTUAL_FINGERPRINT",
        "ACADEMIC_LOOKUP": "SHA256_FINGERPRINT",
        "COLLECTION_REVIEW": "PERCEPTUAL_FINGERPRINT",
        "INTERNAL_FETCH": "METADATA_FINGERPRINT",
    }
    _DEDUPLICATION_POLICIES = {
        "ARCHIVE_REQUEST": "STRICT_DEDUPLICATION",
        "CATALOG_LOOKUP": "STANDARD_DEDUPLICATION",
        "DOCUMENT_RETRIEVAL": "STRICT_DEDUPLICATION",
        "MAP_RETRIEVAL": "STANDARD_DEDUPLICATION",
        "ACADEMIC_LOOKUP": "STRICT_DEDUPLICATION",
        "COLLECTION_REVIEW": "RELAXED_DEDUPLICATION",
        "INTERNAL_FETCH": "STANDARD_DEDUPLICATION",
    }
    _VALIDATION_LEVELS = {
        "ARCHIVE_REQUEST": "STRICT",
        "CATALOG_LOOKUP": "STANDARD",
        "DOCUMENT_RETRIEVAL": "STRICT",
        "MAP_RETRIEVAL": "STANDARD",
        "ACADEMIC_LOOKUP": "STRICT",
        "COLLECTION_REVIEW": "BASIC",
        "INTERNAL_FETCH": "BASIC",
    }

    def __init__(self, source_acquisition_planner):
        if not isinstance(source_acquisition_planner, SourceAcquisitionPlanner):
            raise TypeError(
                "SourceIngestionArchitect requires a SourceAcquisitionPlanner"
            )
        self.source_acquisition_planner = source_acquisition_planner
        self._plans_by_id = {}

    def build_source_ingestion_plan(self, source_acquisition_plan=None):
        source_acquisition_plan = self._plan(source_acquisition_plan)
        self._plans_by_id[source_acquisition_plan.plan_id] = source_acquisition_plan
        batches = self.generate_ingestion_batches(source_acquisition_plan)
        plan_key = "\x00".join(
            [source_acquisition_plan.plan_id, *(batch.batch_id for batch in batches)]
        )
        return SourceIngestionPlan(
            plan_id=(
                f"source_ingestion_plan_"
                f"{sha256(plan_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            source_acquisition_plan_id=source_acquisition_plan.plan_id,
            batches=batches,
            unit_count=sum(len(batch.units) for batch in batches),
        )

    def generate_ingestion_batches(self, source_acquisition_plan=None):
        source_acquisition_plan = self._plan(source_acquisition_plan)
        batches = []
        for acquisition_batch in source_acquisition_plan.batches:
            batch_key = "\x00".join(
                [source_acquisition_plan.plan_id, acquisition_batch.batch_id]
            )
            batch_id = (
                f"ingestion_batch_"
                f"{sha256(batch_key.encode('utf-8')).hexdigest()[:16]}"
            )
            batches.append(
                IngestionBatch(
                    batch_id=batch_id,
                    acquisition_batch_id=acquisition_batch.batch_id,
                    units=self.generate_ingestion_units(acquisition_batch),
                )
            )
        return batches

    def generate_ingestion_units(self, acquisition_batch_or_plan=None):
        """Generate one deterministic ingestion unit per acquisition target."""
        if acquisition_batch_or_plan is None:
            source_acquisition_plan = self._plan(None)
            acquisition_batches = source_acquisition_plan.batches
        elif hasattr(acquisition_batch_or_plan, "targets"):
            acquisition_batches = [acquisition_batch_or_plan]
        else:
            acquisition_batches = acquisition_batch_or_plan.batches

        units = []
        for acquisition_batch in acquisition_batches:
            for position, target in enumerate(acquisition_batch.targets):
                normalization_strategy = self._NORMALIZATION_STRATEGIES[
                    target.acquisition_method
                ]
                fingerprint_strategy = self._FINGERPRINT_STRATEGIES[
                    target.acquisition_method
                ]
                deduplication_policy = self._DEDUPLICATION_POLICIES[
                    target.acquisition_method
                ]
                validation_level = self._VALIDATION_LEVELS[
                    target.acquisition_method
                ]
                unit_key = "\x00".join(
                    [
                        target.target_id,
                        normalization_strategy,
                        fingerprint_strategy,
                        deduplication_policy,
                        validation_level,
                    ]
                )
                units.append(
                    IngestionUnit(
                        unit_id=(
                            f"ingestion_unit_"
                            f"{sha256(unit_key.encode('utf-8')).hexdigest()[:16]}"
                        ),
                        acquisition_target_id=target.target_id,
                        normalization_strategy=normalization_strategy,
                        fingerprint_strategy=fingerprint_strategy,
                        deduplication_policy=deduplication_policy,
                        validation_level=validation_level,
                        position=position,
                    )
                )
        return units

    def assign_normalization_strategies(self, source_acquisition_plan=None):
        source_acquisition_plan = self._plan(source_acquisition_plan)
        return {
            target.target_id: self._NORMALIZATION_STRATEGIES[
                target.acquisition_method
            ]
            for target in self._targets(source_acquisition_plan)
        }

    def assign_fingerprint_strategies(self, source_acquisition_plan=None):
        source_acquisition_plan = self._plan(source_acquisition_plan)
        return {
            target.target_id: self._FINGERPRINT_STRATEGIES[
                target.acquisition_method
            ]
            for target in self._targets(source_acquisition_plan)
        }

    def assign_deduplication_policies(self, source_acquisition_plan=None):
        source_acquisition_plan = self._plan(source_acquisition_plan)
        return {
            target.target_id: self._DEDUPLICATION_POLICIES[
                target.acquisition_method
            ]
            for target in self._targets(source_acquisition_plan)
        }

    def assign_validation_levels(self, source_acquisition_plan=None):
        source_acquisition_plan = self._plan(source_acquisition_plan)
        return {
            target.target_id: self._VALIDATION_LEVELS[target.acquisition_method]
            for target in self._targets(source_acquisition_plan)
        }

    def validate_ingestion_plan(self, plan, source_acquisition_plan=None):
        if plan is None or not plan.batches:
            return False
        source_acquisition_plan = self._validation_plan(
            plan,
            source_acquisition_plan,
        )
        acquisition_batches = source_acquisition_plan.batches
        batches = plan.batches
        expected_targets = [
            target
            for acquisition_batch in acquisition_batches
            for target in acquisition_batch.targets
        ]
        units = [unit for batch in batches for unit in batch.units]
        expected_target_ids = [target.target_id for target in expected_targets]
        unit_target_ids = [unit.acquisition_target_id for unit in units]
        batch_ids = [batch.batch_id for batch in batches]
        batch_acquisition_batch_ids = [
            batch.acquisition_batch_id for batch in batches
        ]
        acquisition_batch_ids = [
            acquisition_batch.batch_id for acquisition_batch in acquisition_batches
        ]
        unit_ids = [unit.unit_id for unit in units]

        if plan.source_acquisition_plan_id != source_acquisition_plan.plan_id:
            return False
        if plan.unit_count != len(units):
            return False
        if len(batch_ids) != len(set(batch_ids)):
            return False
        if len(batch_acquisition_batch_ids) != len(set(batch_acquisition_batch_ids)):
            return False
        if len(unit_ids) != len(set(unit_ids)):
            return False
        if batch_acquisition_batch_ids != acquisition_batch_ids:
            return False
        if set(batch_acquisition_batch_ids) != set(acquisition_batch_ids):
            return False
        if unit_target_ids != expected_target_ids:
            return False
        if len(unit_target_ids) != len(set(unit_target_ids)):
            return False
        if not any(unit.validation_level == "STRICT" for unit in units):
            return False

        expected_normalization = self.assign_normalization_strategies(
            source_acquisition_plan
        )
        expected_fingerprint = self.assign_fingerprint_strategies(
            source_acquisition_plan
        )
        expected_deduplication = self.assign_deduplication_policies(
            source_acquisition_plan
        )
        expected_validation = self.assign_validation_levels(
            source_acquisition_plan
        )
        for batch, acquisition_batch in zip(batches, acquisition_batches):
            if not batch.units:
                return False
            if batch.acquisition_batch_id != acquisition_batch.batch_id:
                return False
            if [unit.position for unit in batch.units] != list(
                range(len(batch.units))
            ):
                return False
            if batch.units != sorted(
                batch.units,
                key=lambda item: (item.position, item.unit_id),
            ):
                return False
            if [unit.acquisition_target_id for unit in batch.units] != [
                target.target_id for target in acquisition_batch.targets
            ]:
                return False
            if any(
                unit.normalization_strategy
                != expected_normalization[unit.acquisition_target_id]
                or unit.fingerprint_strategy
                != expected_fingerprint[unit.acquisition_target_id]
                or unit.deduplication_policy
                != expected_deduplication[unit.acquisition_target_id]
                or unit.validation_level
                != expected_validation[unit.acquisition_target_id]
                or unit.normalization_strategy
                not in self._NORMALIZATION_STRATEGIES.values()
                or unit.fingerprint_strategy
                not in self._FINGERPRINT_STRATEGIES.values()
                or unit.deduplication_policy
                not in self._DEDUPLICATION_POLICIES.values()
                or unit.validation_level not in self._VALIDATION_LEVELS.values()
                or not isinstance(unit.position, int)
                or isinstance(unit.position, bool)
                for unit in batch.units
            ):
                return False
        return True

    def _plan(self, source_acquisition_plan):
        return (
            self.source_acquisition_planner.build_source_acquisition_plan()
            if source_acquisition_plan is None
            else source_acquisition_plan
        )

    def _validation_plan(self, plan, source_acquisition_plan):
        if source_acquisition_plan is not None:
            return source_acquisition_plan
        return self._plans_by_id.get(
            plan.source_acquisition_plan_id
        ) or self._plan(None)

    @staticmethod
    def _targets(source_acquisition_plan):
        return [
            target
            for acquisition_batch in source_acquisition_plan.batches
            for target in acquisition_batch.targets
        ]


__all__ = ["SourceIngestionArchitect"]
