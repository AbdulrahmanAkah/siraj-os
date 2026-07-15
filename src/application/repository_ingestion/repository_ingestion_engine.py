from collections.abc import Sequence
from hashlib import sha256
import json

from src.application.source_ingestion_runtime.models import (
    DeduplicationResult,
    FingerprintResult,
    IngestionExecutionResult,
    NormalizedPayload,
)
from src.application.source_ingestion_runtime.source_ingestion_executor import (
    SourceIngestionExecutor,
)

from .models import RepositoryDocument, RepositoryIngestionResult


class RepositoryIngestionEngine:
    """Populate repository-ready in-memory documents from runtime results."""

    def __init__(self, source_ingestion_executor):
        if not isinstance(source_ingestion_executor, SourceIngestionExecutor):
            raise TypeError(
                "RepositoryIngestionEngine requires a SourceIngestionExecutor"
            )
        self.source_ingestion_executor = source_ingestion_executor

    def ingest_execution_result(self, execution_result):
        if not self.validate_repository_ingestion(execution_result):
            raise ValueError("Invalid ingestion execution result")

        created_documents = self.create_repository_documents(execution_result)
        skipped_duplicates = [
            self.skip_duplicate_document(duplicate)
            for duplicate in self._ordered_duplicates(execution_result)
        ]
        failed_documents = [
            validation.unit_id
            for validation in execution_result.validation_results
            if not validation.is_valid
        ]
        return self.build_repository_ingestion_result(
            execution_result,
            created_documents,
            skipped_duplicates,
            failed_documents,
        )

    def create_repository_documents(self, execution_result):
        normalized_by_unit = {
            payload.unit_id: payload
            for payload in execution_result.normalized_payloads
        }
        fingerprint_by_unit = {
            fingerprint.unit_id: fingerprint
            for fingerprint in execution_result.fingerprints
        }
        duplicate_by_unit = {
            duplicate.unit_id: duplicate
            for duplicate in execution_result.deduplication_results
        }
        documents = []
        for validation in execution_result.validation_results:
            if not validation.is_valid:
                continue
            duplicate = duplicate_by_unit.get(validation.unit_id)
            if duplicate is None or duplicate.is_duplicate:
                continue
            normalized = normalized_by_unit.get(validation.unit_id)
            fingerprint = fingerprint_by_unit.get(validation.unit_id)
            if normalized is None or fingerprint is None:
                continue
            documents.append(
                self.create_document(
                    execution_result,
                    normalized,
                    fingerprint,
                )
            )
        return documents

    def create_document(
        self,
        execution_result,
        normalized_payload,
        fingerprint_result,
    ):
        if not isinstance(normalized_payload, NormalizedPayload):
            raise TypeError("normalized_payload must be a NormalizedPayload")
        if not isinstance(fingerprint_result, FingerprintResult):
            raise TypeError("fingerprint_result must be a FingerprintResult")
        if normalized_payload.unit_id != fingerprint_result.unit_id:
            raise ValueError("Source unit and fingerprint unit must match")
        document_key = "\x00".join(
            [normalized_payload.unit_id, fingerprint_result.fingerprint]
        )
        document_id = (
            f"repository_document_"
            f"{sha256(document_key.encode('utf-8')).hexdigest()[:16]}"
        )
        return RepositoryDocument(
            document_id=document_id,
            source_unit_id=normalized_payload.unit_id,
            fingerprint=fingerprint_result.fingerprint,
            media_type=normalized_payload.normalized_media_type,
            metadata=dict(normalized_payload.normalized_metadata),
            ingested_at=execution_result.execution_id,
        )

    @staticmethod
    def skip_duplicate_document(duplicate_result):
        if not isinstance(duplicate_result, DeduplicationResult):
            raise TypeError("duplicate_result must be a DeduplicationResult")
        return duplicate_result.unit_id

    def validate_repository_ingestion(
        self,
        execution_result,
        repository_result=None,
    ):
        if not isinstance(execution_result, IngestionExecutionResult):
            return False
        validations = execution_result.validation_results
        fingerprints = execution_result.fingerprints
        normalized = execution_result.normalized_payloads
        duplicates = execution_result.deduplication_results
        validation_ids = [item.unit_id for item in validations]
        normalized_ids = [item.unit_id for item in normalized]
        fingerprint_ids = [item.unit_id for item in fingerprints]
        duplicate_ids = [item.unit_id for item in duplicates]
        if execution_result.processed_count != len(validations):
            return False
        if len(validation_ids) != len(set(validation_ids)):
            return False
        if len(normalized_ids) != len(set(normalized_ids)):
            return False
        if len(fingerprint_ids) != len(set(fingerprint_ids)):
            return False
        if len(duplicate_ids) != len(set(duplicate_ids)):
            return False
        validation_id_set = set(validation_ids)
        if not set(normalized_ids).issubset(validation_id_set):
            return False
        if not set(fingerprint_ids).issubset(set(normalized_ids)):
            return False
        if not set(duplicate_ids).issubset(set(fingerprint_ids)):
            return False
        validation_by_unit = {item.unit_id: item for item in validations}
        if any(
            not validation_by_unit[item.unit_id].is_valid
            for item in duplicates
        ):
            return False
        if (
            execution_result.accepted_count
            + execution_result.rejected_count
            + execution_result.duplicate_count
            != execution_result.processed_count
        ):
            return False
        if execution_result.rejected_count != sum(
            not item.is_valid for item in validations
        ):
            return False
        duplicate_by_unit = {item.unit_id: item for item in duplicates}
        accepted_ids = {
            item.unit_id
            for item in validations
            if item.is_valid
            and item.unit_id in duplicate_by_unit
            and not duplicate_by_unit[item.unit_id].is_duplicate
        }
        if not accepted_ids.issubset(set(normalized_ids)):
            return False
        if not accepted_ids.issubset(set(fingerprint_ids)):
            return False
        accepted_count = sum(
            item.is_valid
            and item.unit_id in duplicate_by_unit
            and not duplicate_by_unit[item.unit_id].is_duplicate
            for item in validations
        )
        duplicate_count = sum(
            item.is_valid
            and item.unit_id in duplicate_by_unit
            and duplicate_by_unit[item.unit_id].is_duplicate
            for item in validations
        )
        if execution_result.accepted_count != accepted_count:
            return False
        if execution_result.duplicate_count != duplicate_count:
            return False
        if repository_result is None:
            return True
        if not isinstance(repository_result, RepositoryIngestionResult):
            return False
        created_ids = [
            document.document_id
            for document in repository_result.created_documents
        ]
        if len(created_ids) != len(set(created_ids)):
            return False
        if repository_result.document_count != len(created_ids):
            return False
        if repository_result.execution_id != execution_result.execution_id:
            return False
        expected_skipped = [
            item.unit_id for item in duplicates if item.is_duplicate
        ]
        expected_failed = [item.unit_id for item in validations if not item.is_valid]
        if repository_result.skipped_duplicates != expected_skipped:
            return False
        if repository_result.failed_documents != expected_failed:
            return False
        expected_created = self.create_repository_documents(execution_result)
        if repository_result.created_documents != expected_created:
            return False
        return True

    def build_repository_ingestion_result(
        self,
        execution_result,
        created_documents,
        skipped_duplicates,
        failed_documents,
    ):
        material = {
            "execution_id": execution_result.execution_id,
            "created": [document.document_id for document in created_documents],
            "skipped": list(skipped_duplicates),
            "failed": list(failed_documents),
        }
        result_id = (
            f"repository_ingestion_result_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        result = RepositoryIngestionResult(
            result_id=result_id,
            execution_id=execution_result.execution_id,
            created_documents=list(created_documents),
            skipped_duplicates=list(skipped_duplicates),
            failed_documents=list(failed_documents),
            document_count=len(created_documents),
        )
        if not self.validate_repository_ingestion(execution_result, result):
            raise ValueError("Invalid repository ingestion result")
        return result

    @staticmethod
    def _ordered_duplicates(execution_result) -> Sequence[DeduplicationResult]:
        return [
            duplicate
            for duplicate in execution_result.deduplication_results
            if duplicate.is_duplicate
        ]


__all__ = ["RepositoryIngestionEngine"]
