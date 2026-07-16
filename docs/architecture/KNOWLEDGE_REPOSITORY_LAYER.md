# Canonical Knowledge Repository Layer

## Purpose

Spirit 22 introduces the first formal SIRAJ knowledge repository. It loads
`RepositoryDocument` values produced by repository ingestion and stores
deterministic in-memory `KnowledgeRecord` values as the central source for
future retrieval, claims, events, and reasoning layers.

## Construction

```text
Repository Ingestion
  -> Knowledge Repository
  -> Future Retrieval / Claims / Events / Reasoning
```

`KnowledgeRepository` accepts only `RepositoryIngestionEngine` and
`RepositoryDocument` values. It does not import or invoke claim, reasoning,
timeline, documentary, narrative, or LLM components.

## Models

| Model | Contents |
| --- | --- |
| `KnowledgeRecord` | Deterministic record ID, source document ID, fingerprint, media type, metadata, and deterministic creation marker. |
| `RepositorySnapshot` | Deterministic snapshot ID, record count, and records ordered by `record_id`. |
| `RepositoryLoadResult` | Deterministic load result ID, created records, skipped document IDs, and created record count. |

## Loading rules

- Each new `RepositoryDocument` creates one `KnowledgeRecord`.
- Record IDs derive from `document_id` and `fingerprint` using SHA-256.
- Existing fingerprints are skipped and cannot create a second record.
- Document content is not modified or interpreted.
- `created_at` preserves the document's deterministic ingestion marker.

## Snapshot and validation

Snapshots are sorted by ascending `record_id` and have deterministic IDs.
Validation enforces unique record IDs, unique fingerprints, document linkage,
record counts, record identity, and snapshot consistency.

## Deferred work

This layer is an in-memory repository core. It does not persist to disk or a
database, perform retrieval, extract claims or entities, create events, run
reasoning, or invoke LLM systems. Those are future consumers of snapshots.
