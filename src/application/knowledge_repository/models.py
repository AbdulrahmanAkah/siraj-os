from dataclasses import dataclass, field


@dataclass
class KnowledgeRecord:
    record_id: str
    document_id: str
    fingerprint: str
    media_type: str
    metadata: dict[str, str]
    created_at: str


@dataclass
class RepositorySnapshot:
    snapshot_id: str
    record_count: int
    records: list[KnowledgeRecord] = field(default_factory=list)


@dataclass
class RepositoryLoadResult:
    result_id: str
    created_records: list[KnowledgeRecord] = field(default_factory=list)
    skipped_records: list[str] = field(default_factory=list)
    record_count: int = 0


__all__ = [
    "KnowledgeRecord",
    "RepositoryLoadResult",
    "RepositorySnapshot",
]
