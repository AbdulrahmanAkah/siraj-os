from dataclasses import dataclass, field

from src.application.knowledge_repository.models import KnowledgeRecord


@dataclass
class IndexEntry:
    index_name: str
    key: str
    record_ids: list[str] = field(default_factory=list)


@dataclass
class RetrievalIndex:
    index_id: str
    snapshot_id: str
    records_by_id: dict[str, KnowledgeRecord] = field(default_factory=dict)
    fingerprint_index: dict[str, list[str]] = field(default_factory=dict)
    media_type_index: dict[str, list[str]] = field(default_factory=dict)
    metadata_key_index: dict[str, list[str]] = field(default_factory=dict)
    metadata_value_index: dict[str, list[str]] = field(default_factory=dict)
    entries: list[IndexEntry] = field(default_factory=list)


@dataclass
class RetrievalRequest:
    request_id: str
    fingerprints: list[str] = field(default_factory=list)
    media_types: list[str] = field(default_factory=list)
    metadata_keys: list[str] = field(default_factory=list)
    metadata_values: list[str] = field(default_factory=list)


@dataclass
class RetrievalMatch:
    record_id: str
    record: KnowledgeRecord


@dataclass
class RetrievalResult:
    retrieval_id: str
    request_id: str
    matches: list[RetrievalMatch] = field(default_factory=list)
    match_count: int = 0


__all__ = [
    "IndexEntry",
    "RetrievalIndex",
    "RetrievalMatch",
    "RetrievalRequest",
    "RetrievalResult",
]
