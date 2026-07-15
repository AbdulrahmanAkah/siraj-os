from collections.abc import Sequence
from hashlib import sha256
import json

from src.application.repository_ingestion.models import RepositoryDocument
from src.application.repository_ingestion.repository_ingestion_engine import (
    RepositoryIngestionEngine,
)

from .models import KnowledgeRecord, RepositoryLoadResult, RepositorySnapshot


class KnowledgeRepository:
    """Deterministic in-memory knowledge repository core."""

    def __init__(self, repository_ingestion_engine):
        if not isinstance(repository_ingestion_engine, RepositoryIngestionEngine):
            raise TypeError(
                "KnowledgeRepository requires a RepositoryIngestionEngine"
            )
        self.repository_ingestion_engine = repository_ingestion_engine
        self._documents_by_id = {}
        self._records_by_id = {}
        self._record_id_by_fingerprint = {}

    def load_repository_documents(self, documents):
        if not isinstance(documents, Sequence) or isinstance(documents, (str, bytes)):
            raise TypeError("documents must be a sequence of RepositoryDocument")
        if not all(isinstance(document, RepositoryDocument) for document in documents):
            raise TypeError("documents must contain only RepositoryDocument values")

        created_records = []
        skipped_records = []
        for document in documents:
            self._documents_by_id[document.document_id] = document
            if document.fingerprint in self._record_id_by_fingerprint:
                skipped_records.append(self.skip_existing_record(document))
                continue
            record = self.create_knowledge_record(document)
            self._records_by_id[record.record_id] = record
            self._record_id_by_fingerprint[record.fingerprint] = record.record_id
            created_records.append(record)

        result = RepositoryLoadResult(
            result_id=self._build_load_result_id(
                created_records,
                skipped_records,
            ),
            created_records=list(created_records),
            skipped_records=list(skipped_records),
            record_count=len(created_records),
        )
        if not self.validate_repository():
            raise ValueError("Repository validation failed after loading documents")
        return result

    def create_knowledge_record(self, document):
        if not isinstance(document, RepositoryDocument):
            raise TypeError("document must be a RepositoryDocument")
        record_key = "\x00".join([document.document_id, document.fingerprint])
        record_id = (
            f"knowledge_record_"
            f"{sha256(record_key.encode('utf-8')).hexdigest()[:16]}"
        )
        return KnowledgeRecord(
            record_id=record_id,
            document_id=document.document_id,
            fingerprint=document.fingerprint,
            media_type=document.media_type,
            metadata=dict(document.metadata),
            created_at=document.ingested_at,
        )

    def skip_existing_record(self, document):
        if not isinstance(document, RepositoryDocument):
            raise TypeError("document must be a RepositoryDocument")
        return document.document_id

    def build_snapshot(self):
        records = sorted(
            self._records_by_id.values(),
            key=lambda record: record.record_id,
        )
        snapshot_material = [
            {
                "record_id": record.record_id,
                "document_id": record.document_id,
                "fingerprint": record.fingerprint,
            }
            for record in records
        ]
        snapshot_id = (
            f"repository_snapshot_"
            f"{sha256(json.dumps(snapshot_material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        snapshot = RepositorySnapshot(
            snapshot_id=snapshot_id,
            record_count=len(records),
            records=list(records),
        )
        if not self.validate_repository(snapshot):
            raise ValueError("Repository snapshot validation failed")
        return snapshot

    def validate_repository(self, snapshot=None):
        records = list(self._records_by_id.values())
        record_ids = [record.record_id for record in records]
        fingerprints = [record.fingerprint for record in records]
        if len(record_ids) != len(set(record_ids)):
            return False
        if len(fingerprints) != len(set(fingerprints)):
            return False
        if any(
            not isinstance(record, KnowledgeRecord)
            or record.document_id not in self._documents_by_id
            or self._record_id(record.document_id, record.fingerprint)
            != record.record_id
            for record in records
        ):
            return False
        if len(self._record_id_by_fingerprint) != len(records):
            return False
        if any(
            self._record_id_by_fingerprint.get(record.fingerprint)
            != record.record_id
            for record in records
        ):
            return False
        if snapshot is None:
            return True
        if not isinstance(snapshot, RepositorySnapshot):
            return False
        expected_records = sorted(records, key=lambda record: record.record_id)
        if snapshot.records != expected_records:
            return False
        if snapshot.record_count != len(snapshot.records):
            return False
        if [record.record_id for record in snapshot.records] != sorted(
            record_ids
        ):
            return False
        return snapshot.snapshot_id == self._snapshot_id(expected_records)

    def export_repository_snapshot(self, snapshot=None):
        return self.build_snapshot() if snapshot is None else snapshot

    @staticmethod
    def _record_id(document_id, fingerprint):
        record_key = "\x00".join([document_id, fingerprint])
        return (
            f"knowledge_record_"
            f"{sha256(record_key.encode('utf-8')).hexdigest()[:16]}"
        )

    @classmethod
    def _snapshot_id(cls, records):
        snapshot_material = [
            {
                "record_id": record.record_id,
                "document_id": record.document_id,
                "fingerprint": record.fingerprint,
            }
            for record in records
        ]
        return (
            f"repository_snapshot_"
            f"{sha256(json.dumps(snapshot_material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )

    @staticmethod
    def _build_load_result_id(created_records, skipped_records):
        material = {
            "created": [record.record_id for record in created_records],
            "skipped": list(skipped_records),
        }
        return (
            f"repository_load_result_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )


__all__ = ["KnowledgeRepository"]
