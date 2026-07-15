from dataclasses import dataclass, field


@dataclass
class RepositoryDocument:
    document_id: str
    source_unit_id: str
    fingerprint: str
    media_type: str
    metadata: dict[str, str]
    ingested_at: str


@dataclass
class RepositoryIngestionResult:
    result_id: str
    execution_id: str
    created_documents: list[RepositoryDocument] = field(default_factory=list)
    skipped_duplicates: list[str] = field(default_factory=list)
    failed_documents: list[str] = field(default_factory=list)
    document_count: int = 0


__all__ = ["RepositoryDocument", "RepositoryIngestionResult"]
