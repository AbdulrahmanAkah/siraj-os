from dataclasses import dataclass, field

from src.application.knowledge_repository.models import KnowledgeRecord


@dataclass
class QueryRequest:
    query_id: str
    fingerprints: list[str] = field(default_factory=list)
    media_types: list[str] = field(default_factory=list)
    metadata_filters: dict[str, str] = field(default_factory=dict)


@dataclass
class QueryResult:
    result_id: str
    matched_records: list[KnowledgeRecord] = field(default_factory=list)
    match_count: int = 0


__all__ = ["QueryRequest", "QueryResult"]
