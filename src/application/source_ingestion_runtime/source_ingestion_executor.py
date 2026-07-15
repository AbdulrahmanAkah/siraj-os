from collections.abc import Mapping, Sequence
from hashlib import sha256
import json

from src.application.source_ingestion_architecture.source_ingestion_architect import (
    SourceIngestionArchitect,
)

from .models import (
    DeduplicationResult,
    FingerprintResult,
    IngestionExecutionResult,
    IngestionPayload,
    NormalizedPayload,
    ValidationResult,
)


class SourceIngestionExecutor:
    """Executes deterministic ingestion preparation over local memory only."""

    _NORMALIZATION_STRATEGIES = {
        "DOCUMENT_NORMALIZATION",
        "IMAGE_NORMALIZATION",
        "MAP_NORMALIZATION",
        "METADATA_NORMALIZATION",
        "ARCHIVE_NORMALIZATION",
    }
    _FINGERPRINT_STRATEGIES = {
        "SHA256_FINGERPRINT",
        "PERCEPTUAL_FINGERPRINT",
        "METADATA_FINGERPRINT",
    }
    _DEDUPLICATION_POLICIES = {
        "STRICT_DEDUPLICATION",
        "STANDARD_DEDUPLICATION",
        "RELAXED_DEDUPLICATION",
    }
    _VALIDATION_LEVELS = {"STRICT", "STANDARD", "BASIC"}

    def __init__(self, source_ingestion_architect):
        if not isinstance(source_ingestion_architect, SourceIngestionArchitect):
            raise TypeError(
                "SourceIngestionExecutor requires a SourceIngestionArchitect"
            )
        self.source_ingestion_architect = source_ingestion_architect

    def execute_ingestion(self, ingestion_plan, payloads):
        self.validate_runtime_inputs_or_raise(ingestion_plan, payloads)
        units = self._ordered_units(ingestion_plan)
        payload_by_target = payloads
        normalized_payloads = self.normalize_payloads(
            ingestion_plan,
            payload_by_target,
        )
        normalized_by_unit = {
            payload.unit_id: payload for payload in normalized_payloads
        }
        validation_results = self.validate_payloads(
            ingestion_plan,
            payload_by_target,
            normalized_by_unit,
        )
        validation_by_unit = {
            result.unit_id: result for result in validation_results
        }
        fingerprints = self.generate_fingerprints(
            ingestion_plan,
            normalized_payloads,
        )
        deduplication_results = self.evaluate_deduplication(
            ingestion_plan,
            fingerprints,
            validation_by_unit,
        )
        duplicate_by_unit = {
            result.unit_id: result for result in deduplication_results
        }
        accepted_count = sum(
            validation_by_unit[unit.unit_id].is_valid
            and not duplicate_by_unit.get(unit.unit_id).is_duplicate
            for unit in units
        )
        duplicate_count = sum(
            validation_by_unit[unit.unit_id].is_valid
            and duplicate_by_unit.get(unit.unit_id).is_duplicate
            for unit in units
        )
        rejected_count = sum(
            not validation_by_unit[unit.unit_id].is_valid for unit in units
        )
        return self.build_execution_result(
            ingestion_plan,
            normalized_payloads,
            fingerprints,
            deduplication_results,
            validation_results,
            accepted_count,
            rejected_count,
            duplicate_count,
            payload_by_target,
        )

    def normalize_payloads(self, ingestion_plan, payloads):
        payloads_by_target = payloads
        normalized = []
        for unit in self._ordered_units(ingestion_plan):
            payload = payloads_by_target.get(unit.acquisition_target_id)
            if payload is None or unit.normalization_strategy not in self._NORMALIZATION_STRATEGIES:
                continue
            normalized.append(self.normalize_payload(unit, payload))
        return normalized

    def normalize_payload(self, unit, payload):
        strategy = unit.normalization_strategy
        if strategy not in self._NORMALIZATION_STRATEGIES:
            raise ValueError("UNKNOWN_NORMALIZATION_STRATEGY")
        if not isinstance(payload.content_bytes, bytes):
            raise TypeError("content_bytes must be bytes")
        media_type = payload.media_type.strip().lower()
        metadata = self._normalize_metadata(payload.metadata)
        return NormalizedPayload(
            unit_id=unit.unit_id,
            normalized_bytes=payload.content_bytes,
            normalized_media_type=media_type,
            normalized_metadata=metadata,
        )

    def generate_fingerprints(self, ingestion_plan, normalized_payloads):
        units_by_id = {unit.unit_id: unit for unit in self._ordered_units(ingestion_plan)}
        return [
            self.generate_fingerprint(
                normalized_payload,
                units_by_id[normalized_payload.unit_id].fingerprint_strategy,
            )
            for normalized_payload in normalized_payloads
        ]

    def generate_fingerprint(self, normalized_payload, fingerprint_strategy):
        if fingerprint_strategy not in self._FINGERPRINT_STRATEGIES:
            raise ValueError("UNKNOWN_FINGERPRINT_STRATEGY")
        if fingerprint_strategy == "SHA256_FINGERPRINT":
            material = normalized_payload.normalized_bytes
        elif fingerprint_strategy == "PERCEPTUAL_FINGERPRINT":
            material = (
                normalized_payload.normalized_media_type.encode("utf-8")
                + b"\x00"
                + normalized_payload.normalized_bytes
            )
        else:
            material = json.dumps(
                normalized_payload.normalized_metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        return FingerprintResult(
            unit_id=normalized_payload.unit_id,
            fingerprint=sha256(material).hexdigest(),
            fingerprint_strategy=fingerprint_strategy,
        )

    def evaluate_deduplication(
        self,
        ingestion_plan,
        fingerprints,
        validation_results=None,
    ):
        units_by_id = {unit.unit_id: unit for unit in self._ordered_units(ingestion_plan)}
        valid_by_unit = {
            unit_id: result.is_valid
            for unit_id, result in (validation_results or {}).items()
        }
        accepted_by_fingerprint = {}
        results = []
        for fingerprint_result in fingerprints:
            unit = units_by_id[fingerprint_result.unit_id]
            is_valid = valid_by_unit.get(unit.unit_id, True)
            duplicate_of = None
            if is_valid:
                duplicate_of = accepted_by_fingerprint.get(
                    fingerprint_result.fingerprint
                )
                if duplicate_of is None:
                    accepted_by_fingerprint[fingerprint_result.fingerprint] = (
                        unit.unit_id
                    )
            results.append(
                DeduplicationResult(
                    unit_id=unit.unit_id,
                    fingerprint=fingerprint_result.fingerprint,
                    is_duplicate=duplicate_of is not None,
                    duplicate_of_unit_id=duplicate_of,
                )
            )
        return results

    def validate_payloads(self, ingestion_plan, payloads, normalized_by_unit=None):
        normalized_by_unit = normalized_by_unit or {}
        return [
            self.validate_payload(
                unit,
                payloads.get(unit.acquisition_target_id),
                normalized_by_unit.get(unit.unit_id),
            )
            for unit in self._ordered_units(ingestion_plan)
        ]

    def validate_payload(self, unit, payload, normalized_payload=None):
        errors = []
        if unit.normalization_strategy not in self._NORMALIZATION_STRATEGIES:
            errors.append("UNKNOWN_NORMALIZATION_STRATEGY")
        if unit.fingerprint_strategy not in self._FINGERPRINT_STRATEGIES:
            errors.append("UNKNOWN_FINGERPRINT_STRATEGY")
        if unit.deduplication_policy not in self._DEDUPLICATION_POLICIES:
            errors.append("UNKNOWN_DEDUPLICATION_POLICY")
        if unit.validation_level not in self._VALIDATION_LEVELS:
            errors.append("UNKNOWN_VALIDATION_LEVEL")
        if payload is None:
            errors.append("MISSING_PAYLOAD")
        else:
            if payload.target_id != unit.acquisition_target_id:
                errors.append("TARGET_ID_MISMATCH")
            if normalized_payload is not None:
                if unit.validation_level in {"STANDARD", "STRICT"}:
                    if not normalized_payload.normalized_media_type:
                        errors.append("EMPTY_MEDIA_TYPE")
                if unit.validation_level == "STRICT":
                    if not normalized_payload.normalized_bytes:
                        errors.append("EMPTY_CONTENT")
        return ValidationResult(
            unit_id=unit.unit_id,
            is_valid=not errors,
            validation_level=unit.validation_level,
            errors=errors,
        )

    def build_execution_result(
        self,
        ingestion_plan,
        normalized_payloads,
        fingerprints,
        deduplication_results,
        validation_results,
        accepted_count,
        rejected_count,
        duplicate_count,
        payloads,
    ):
        units = self._ordered_units(ingestion_plan)
        fingerprint_by_unit = {
            result.unit_id: result.fingerprint for result in fingerprints
        }
        validation_by_unit = {
            result.unit_id: result for result in validation_results
        }
        dedup_by_unit = {
            result.unit_id: result for result in deduplication_results
        }
        execution_material = {
            "plan": ingestion_plan.plan_id,
            "units": [
                {
                    "unit": unit.unit_id,
                    "target": unit.acquisition_target_id,
                    "payload_target": (
                        payloads[unit.acquisition_target_id].target_id
                        if unit.acquisition_target_id in payloads
                        else None
                    ),
                    "fingerprint": fingerprint_by_unit.get(unit.unit_id),
                    "valid": validation_by_unit[unit.unit_id].is_valid,
                    "errors": validation_by_unit[unit.unit_id].errors,
                    "duplicate": dedup_by_unit.get(unit.unit_id).is_duplicate
                    if unit.unit_id in dedup_by_unit
                    else False,
                }
                for unit in units
            ],
        }
        execution_id = (
            f"ingestion_execution_"
            f"{sha256(json.dumps(execution_material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode('utf-8')).hexdigest()[:16]}"
        )
        return IngestionExecutionResult(
            execution_id=execution_id,
            source_ingestion_plan_id=ingestion_plan.plan_id,
            normalized_payloads=normalized_payloads,
            fingerprints=fingerprints,
            deduplication_results=deduplication_results,
            validation_results=validation_results,
            processed_count=len(units),
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
        )

    def validate_runtime_inputs(self, ingestion_plan, payloads):
        try:
            if not self.source_ingestion_architect.validate_ingestion_plan(
                ingestion_plan
            ):
                return False
        except (AttributeError, TypeError):
            return False
        if not isinstance(payloads, Mapping):
            return False
        target_ids = {
            unit.acquisition_target_id
            for unit in self._ordered_units(ingestion_plan)
        }
        if any(key not in target_ids for key in payloads):
            return False
        return all(
            isinstance(key, str)
            and isinstance(payload, IngestionPayload)
            and payload.target_id == key
            and isinstance(payload.content_bytes, bytes)
            and isinstance(payload.media_type, str)
            and isinstance(payload.metadata, dict)
            and all(
                isinstance(metadata_key, str)
                and isinstance(metadata_value, str)
                for metadata_key, metadata_value in payload.metadata.items()
            )
            for key, payload in payloads.items()
        )

    def validate_runtime_inputs_or_raise(self, ingestion_plan, payloads):
        if not self.validate_runtime_inputs(ingestion_plan, payloads):
            raise ValueError("Invalid ingestion runtime inputs")

    @staticmethod
    def _normalize_metadata(metadata):
        return {
            key.strip().lower(): value.strip()
            for key, value in sorted(metadata.items(), key=lambda item: item[0])
        }

    @staticmethod
    def _ordered_units(ingestion_plan):
        return [
            unit
            for batch in ingestion_plan.batches
            for unit in batch.units
        ]


__all__ = ["SourceIngestionExecutor"]
