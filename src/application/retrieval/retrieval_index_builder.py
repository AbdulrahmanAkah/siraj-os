from hashlib import sha256
import json

from src.application.knowledge_repository.models import (
    KnowledgeRecord,
    RepositorySnapshot,
)
from src.application.repository_query.models import QueryRequest, QueryResult
from src.application.repository_query.repository_query_engine import (
    RepositoryQueryEngine,
)

from .models import IndexEntry, RetrievalIndex


class RetrievalIndexBuilder:
    """Builds deterministic exact-match indexes from repository query results."""

    def __init__(self, repository_query_engine):
        if not isinstance(repository_query_engine, RepositoryQueryEngine):
            raise TypeError(
                "RetrievalIndexBuilder requires a RepositoryQueryEngine"
            )
        self.repository_query_engine = repository_query_engine

    def build_retrieval_index(self, source=None):
        records, snapshot_id = self._source_records(source)
        records_by_id = {record.record_id: record for record in records}
        fingerprint_index = self._build_value_index(
            records,
            lambda record: [record.fingerprint],
        )
        media_type_index = self._build_value_index(
            records,
            lambda record: [record.media_type],
        )
        metadata_key_index = self._build_value_index(
            records,
            lambda record: list(record.metadata),
        )
        metadata_value_index = self._build_value_index(
            records,
            lambda record: list(record.metadata.values()),
        )
        entries = self._build_entries(
            fingerprint_index,
            media_type_index,
            metadata_key_index,
            metadata_value_index,
        )
        index_material = {
            "snapshot_id": snapshot_id,
            "entries": [
                {
                    "index_name": entry.index_name,
                    "key": entry.key,
                    "record_ids": entry.record_ids,
                }
                for entry in entries
            ],
        }
        index_id = (
            f"retrieval_index_"
            f"{sha256(json.dumps(index_material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        index = RetrievalIndex(
            index_id=index_id,
            snapshot_id=snapshot_id,
            records_by_id=records_by_id,
            fingerprint_index=fingerprint_index,
            media_type_index=media_type_index,
            metadata_key_index=metadata_key_index,
            metadata_value_index=metadata_value_index,
            entries=entries,
        )
        if not self.validate_index(index):
            raise ValueError("Retrieval index validation failed")
        return index

    def validate_index(self, index):
        if not isinstance(index, RetrievalIndex):
            return False
        record_ids = list(index.records_by_id)
        if len(record_ids) != len(set(record_ids)):
            return False
        if any(
            not isinstance(record, KnowledgeRecord)
            or record_id != record.record_id
            for record_id, record in index.records_by_id.items()
        ):
            return False
        expected_maps = {
            "fingerprint": index.fingerprint_index,
            "media_type": index.media_type_index,
            "metadata_key": index.metadata_key_index,
            "metadata_value": index.metadata_value_index,
        }
        for index_name, value_map in expected_maps.items():
            if any(
                value_map[key] != sorted(set(value_map[key]))
                or any(record_id not in index.records_by_id for record_id in value_map[key])
                for key in value_map
            ):
                return False
            expected = self._build_value_index(
                list(index.records_by_id.values()),
                self._extractor(index_name),
            )
            if value_map != expected:
                return False
        expected_entries = self._build_entries(
            index.fingerprint_index,
            index.media_type_index,
            index.metadata_key_index,
            index.metadata_value_index,
        )
        if index.entries != expected_entries:
            return False
        entry_keys = [
            (entry.index_name, entry.key)
            for entry in index.entries
        ]
        if len(entry_keys) != len(set(entry_keys)):
            return False
        return index.index_id == self._index_id(index.snapshot_id, index.entries)

    def _source_records(self, source):
        if isinstance(source, RepositorySnapshot):
            query_result = self.repository_query_engine.query_repository(
                QueryRequest(query_id="retrieval_index_build"),
                source,
            )
            return query_result.matched_records, source.snapshot_id
        if isinstance(source, QueryResult):
            return source.matched_records, source.result_id
        if source is not None:
            records = list(source)
            if not all(isinstance(record, KnowledgeRecord) for record in records):
                raise TypeError("index source must contain KnowledgeRecord values")
            return records, "record_source_" + sha256(
                json.dumps(
                    [record.record_id for record in records],
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]
        query_result = self.repository_query_engine.query_repository(
            QueryRequest(query_id="retrieval_index_build")
        )
        return query_result.matched_records, query_result.result_id

    @staticmethod
    def _build_value_index(records, extractor):
        value_map = {}
        for record in records:
            for value in extractor(record):
                value_map.setdefault(value, []).append(record.record_id)
        return {
            key: sorted(set(record_ids))
            for key, record_ids in sorted(value_map.items())
        }

    @staticmethod
    def _extractor(index_name):
        return {
            "fingerprint": lambda record: [record.fingerprint],
            "media_type": lambda record: [record.media_type],
            "metadata_key": lambda record: list(record.metadata),
            "metadata_value": lambda record: list(record.metadata.values()),
        }[index_name]

    @classmethod
    def _build_entries(
        cls,
        fingerprint_index,
        media_type_index,
        metadata_key_index,
        metadata_value_index,
    ):
        entries = []
        for index_name, value_map in (
            ("fingerprint", fingerprint_index),
            ("media_type", media_type_index),
            ("metadata_key", metadata_key_index),
            ("metadata_value", metadata_value_index),
        ):
            entries.extend(
                IndexEntry(index_name, key, list(record_ids))
                for key, record_ids in value_map.items()
            )
        return entries

    @staticmethod
    def _index_id(snapshot_id, entries):
        material = {
            "snapshot_id": snapshot_id,
            "entries": [
                {
                    "index_name": entry.index_name,
                    "key": entry.key,
                    "record_ids": entry.record_ids,
                }
                for entry in entries
            ],
        }
        return (
            f"retrieval_index_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )


__all__ = ["RetrievalIndexBuilder"]
