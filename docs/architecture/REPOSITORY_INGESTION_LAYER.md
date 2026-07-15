# Canonical Repository Ingestion Layer

## Purpose

Spirit 21 transforms an `IngestionExecutionResult` into deterministic,
repository-ready `RepositoryDocument` objects. This is the first layer that
creates knowledge-repository objects, but it does not perform reasoning,
claim extraction, entity extraction, event creation, or persistence.

## Construction

```text
Source Ingestion Runtime
  -> Repository Ingestion
  -> Repository
```

`RepositoryIngestionEngine` accepts only `SourceIngestionExecutor`. It consumes
an execution result produced from local in-memory payloads and returns an
in-memory `RepositoryIngestionResult`. No repository implementation is called.

## Models

| Model | Contents |
| --- | --- |
| `RepositoryDocument` | Deterministic document ID, source-unit reference, fingerprint, normalized media type, normalized metadata, and deterministic ingestion marker. |
| `RepositoryIngestionResult` | Deterministic result ID, execution reference, created documents, skipped duplicate unit IDs, failed unit IDs, and document count. |

## Population rules

- Each valid, non-duplicate runtime unit creates exactly one document.
- Duplicate units are recorded in `skipped_duplicates` and never create documents.
- Rejected units are recorded in `failed_documents` and never create documents.
- Document IDs are derived from `source_unit_id` and fingerprint using SHA-256.
- `ingested_at` is the execution ID, providing a deterministic Phase 1 marker
  instead of a wall-clock timestamp.
- Document metadata and media type come from normalized runtime payloads.

## Boundary rules

This layer does not extract claims or entities, create events, reason over
content, call LLMs, perform network access, write databases, or mutate a
persistent repository. Future persistence can consume the validated result.
