from collections.abc import Sequence
from hashlib import sha256
import json

from .models import (
    RetrievalIndex,
    RetrievalMatch,
    RetrievalRequest,
    RetrievalResult,
)
from .retrieval_index_builder import RetrievalIndexBuilder


class RetrievalRuntimeEngine:
    """Executes deterministic retrieval using only a built RetrievalIndex."""

    def __init__(self, retrieval_index_builder):
        if not isinstance(retrieval_index_builder, RetrievalIndexBuilder):
            raise TypeError(
                "RetrievalRuntimeEngine requires a RetrievalIndexBuilder"
            )
        self.retrieval_index_builder = retrieval_index_builder

    def execute_retrieval(self, request, retrieval_index=None):
        if retrieval_index is None:
            retrieval_index = self.retrieval_index_builder.build_retrieval_index()
        if not self.validate_retrieval_request(request):
            raise ValueError("Invalid retrieval request")
        if not self.validate_retrieval_index(retrieval_index):
            raise ValueError("Invalid retrieval index")
        record_ids = self._match_record_ids(request, retrieval_index)
        matches = [
            RetrievalMatch(record_id, retrieval_index.records_by_id[record_id])
            for record_id in record_ids
        ]
        return self.build_retrieval_result(request, matches)

    def retrieve_by_fingerprint(self, fingerprints, retrieval_index=None):
        request = self._field_request("fingerprint", fingerprints)
        return self.execute_retrieval(request, retrieval_index)

    def retrieve_by_media_type(self, media_types, retrieval_index=None):
        request = self._field_request("media_type", media_types)
        return self.execute_retrieval(request, retrieval_index)

    def retrieve_by_metadata_key(self, metadata_keys, retrieval_index=None):
        request = self._field_request("metadata_key", metadata_keys)
        return self.execute_retrieval(request, retrieval_index)

    def retrieve_by_metadata_value(self, metadata_values, retrieval_index=None):
        request = self._field_request("metadata_value", metadata_values)
        return self.execute_retrieval(request, retrieval_index)

    def validate_retrieval_request(self, request):
        if not isinstance(request, RetrievalRequest):
            return False
        if not isinstance(request.request_id, str) or not request.request_id:
            return False
        for values in (
            request.fingerprints,
            request.media_types,
            request.metadata_keys,
            request.metadata_values,
        ):
            if not self._valid_string_sequence(values):
                return False
            if len(values) != len(set(values)):
                return False
        return True

    def validate_retrieval_index(self, retrieval_index):
        return self.retrieval_index_builder.validate_index(retrieval_index)

    def build_retrieval_result(self, request, matches):
        if not self.validate_retrieval_request(request):
            raise ValueError("Invalid retrieval request")
        ordered_matches = sorted(matches, key=lambda match: match.record_id)
        match_ids = [match.record_id for match in ordered_matches]
        if len(match_ids) != len(set(match_ids)):
            raise ValueError("Duplicate retrieval matches are forbidden")
        if any(
            match.record_id != match.record.record_id
            for match in ordered_matches
        ):
            raise ValueError("Retrieval match record linkage is invalid")
        result_material = {
            "request_id": request.request_id,
            "record_ids": match_ids,
        }
        retrieval_id = (
            f"retrieval_result_"
            f"{sha256(json.dumps(result_material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        return RetrievalResult(
            retrieval_id=retrieval_id,
            request_id=request.request_id,
            matches=ordered_matches,
            match_count=len(ordered_matches),
        )

    @staticmethod
    def _match_record_ids(request, retrieval_index):
        candidate_sets = []
        for values, value_index in (
            (request.fingerprints, retrieval_index.fingerprint_index),
            (request.media_types, retrieval_index.media_type_index),
            (request.metadata_keys, retrieval_index.metadata_key_index),
            (request.metadata_values, retrieval_index.metadata_value_index),
        ):
            if values:
                candidate_sets.append(
                    set(
                        record_id
                        for value in values
                        for record_id in value_index.get(value, [])
                    )
                )
        if not candidate_sets:
            return sorted(retrieval_index.records_by_id)
        return sorted(set.intersection(*candidate_sets))

    @staticmethod
    def _valid_string_sequence(value):
        return isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and all(
            isinstance(item, str) for item in value
        )

    @classmethod
    def _field_request(cls, field_name, values):
        if isinstance(values, RetrievalRequest):
            return values
        if isinstance(values, str):
            values = [values]
        else:
            values = list(values)
        return RetrievalRequest(
            request_id=cls._generated_request_id(field_name, values),
            fingerprints=values if field_name == "fingerprint" else [],
            media_types=values if field_name == "media_type" else [],
            metadata_keys=values if field_name == "metadata_key" else [],
            metadata_values=values if field_name == "metadata_value" else [],
        )

    @staticmethod
    def _generated_request_id(prefix, values):
        material = json.dumps(values, sort_keys=True, separators=(",", ":"))
        return f"{prefix}_retrieval_{sha256(material.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["RetrievalRuntimeEngine"]
