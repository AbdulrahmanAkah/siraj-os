from dataclasses import dataclass, field


@dataclass
class IngestionPayload:
    target_id: str
    content_bytes: bytes
    media_type: str
    metadata: dict[str, str]


@dataclass
class NormalizedPayload:
    unit_id: str
    normalized_bytes: bytes
    normalized_media_type: str
    normalized_metadata: dict[str, str]


@dataclass
class FingerprintResult:
    unit_id: str
    fingerprint: str
    fingerprint_strategy: str


@dataclass
class DeduplicationResult:
    unit_id: str
    fingerprint: str
    is_duplicate: bool
    duplicate_of_unit_id: str | None


@dataclass
class ValidationResult:
    unit_id: str
    is_valid: bool
    validation_level: str
    errors: list[str] = field(default_factory=list)


@dataclass
class IngestionExecutionResult:
    execution_id: str
    source_ingestion_plan_id: str
    normalized_payloads: list[NormalizedPayload] = field(default_factory=list)
    fingerprints: list[FingerprintResult] = field(default_factory=list)
    deduplication_results: list[DeduplicationResult] = field(default_factory=list)
    validation_results: list[ValidationResult] = field(default_factory=list)
    processed_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0


__all__ = [
    "DeduplicationResult",
    "FingerprintResult",
    "IngestionExecutionResult",
    "IngestionPayload",
    "NormalizedPayload",
    "ValidationResult",
]
