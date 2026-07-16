from collections.abc import Sequence
from hashlib import sha256
import json

from src.application.knowledge_repository.knowledge_repository import (
    KnowledgeRepository,
)
from src.application.knowledge_repository.models import (
    KnowledgeRecord,
    RepositorySnapshot,
)

from .models import QueryRequest, QueryResult


class RepositoryQueryEngine:
    """Performs deterministic exact queries over the knowledge repository."""

    def __init__(self, knowledge_repository):
        if not isinstance(knowledge_repository, KnowledgeRepository):
            raise TypeError("RepositoryQueryEngine requires a KnowledgeRepository")
        self.knowledge_repository = knowledge_repository

    def query_by_fingerprint(self, fingerprints, snapshot=None):
        request = self._field_request("fingerprint", fingerprints)
        return self.query_repository(request, snapshot)

    def query_by_media_type(self, media_types, snapshot=None):
        request = self._field_request("media_type", media_types)
        return self.query_repository(request, snapshot)

    def query_by_metadata(self, metadata_filters, snapshot=None):
        if isinstance(metadata_filters, QueryRequest):
            request = metadata_filters
        else:
            request = QueryRequest(
                query_id=self._generated_query_id(
                    "metadata",
                    metadata_filters,
                ),
                metadata_filters=dict(metadata_filters),
            )
        return self.query_repository(request, snapshot)

    def query_repository(self, query_request, snapshot=None):
        if not self.validate_query(query_request, snapshot):
            raise ValueError("Invalid query request")
        records = (
            snapshot.records
            if snapshot is not None
            else self.knowledge_repository.build_snapshot().records
        )
        matched_records = [
            record
            for record in records
            if self._matches(record, query_request)
        ]
        matched_records.sort(key=lambda record: record.record_id)
        return self.build_query_result(query_request, matched_records)

    def validate_query(self, query_request, snapshot=None):
        if not isinstance(query_request, QueryRequest):
            return False
        if not isinstance(query_request.query_id, str) or not query_request.query_id:
            return False
        if not self._valid_string_sequence(query_request.fingerprints):
            return False
        if not self._valid_string_sequence(query_request.media_types):
            return False
        if not isinstance(query_request.metadata_filters, dict):
            return False
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            for key, value in query_request.metadata_filters.items()
        ):
            return False
        if len(query_request.fingerprints) != len(
            set(query_request.fingerprints)
        ):
            return False
        if len(query_request.media_types) != len(set(query_request.media_types)):
            return False
        if snapshot is None:
            return self.knowledge_repository.validate_repository()
        return isinstance(snapshot, RepositorySnapshot) and self.knowledge_repository.validate_repository(snapshot)

    def build_query_result(self, query_request, matched_records):
        if not self.validate_query(query_request):
            raise ValueError("Invalid query request")
        ordered_records = sorted(
            matched_records,
            key=lambda record: record.record_id,
        )
        if any(not isinstance(record, KnowledgeRecord) for record in ordered_records):
            raise TypeError("matched_records must contain KnowledgeRecord values")
        record_ids = [record.record_id for record in ordered_records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Duplicate query results are forbidden")
        result_material = {
            "query_id": query_request.query_id,
            "record_ids": record_ids,
        }
        result_id = (
            f"repository_query_result_"
            f"{sha256(json.dumps(result_material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        return QueryResult(
            result_id=result_id,
            matched_records=ordered_records,
            match_count=len(ordered_records),
        )

    @staticmethod
    def _matches(record, query_request):
        return (
            (
                not query_request.fingerprints
                or record.fingerprint in set(query_request.fingerprints)
            )
            and (
                not query_request.media_types
                or record.media_type in set(query_request.media_types)
            )
            and all(
                record.metadata.get(key) == value
                for key, value in query_request.metadata_filters.items()
            )
        )

    @staticmethod
    def _valid_string_sequence(value):
        return isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and all(
            isinstance(item, str) for item in value
        )

    @classmethod
    def _field_request(cls, field_name, values):
        if isinstance(values, QueryRequest):
            return values
        if isinstance(values, str):
            values = [values]
        else:
            values = list(values)
        return QueryRequest(
            query_id=cls._generated_query_id(field_name, values),
            fingerprints=values if field_name == "fingerprint" else [],
            media_types=values if field_name == "media_type" else [],
        )

    @staticmethod
    def _generated_query_id(prefix, value):
        material = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return f"{prefix}_query_{sha256(material.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["RepositoryQueryEngine"]
