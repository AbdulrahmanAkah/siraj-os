# Canonical Retrieval Layer

## Purpose

Spirit 24–25 adds the first complete indexed retrieval path above the
repository query engine. `RetrievalIndexBuilder` creates deterministic exact
indexes, and `RetrievalRuntimeEngine` executes requests using those indexes
only.

## Construction

```text
Knowledge Repository
  -> Repository Query Engine
  -> Retrieval Index
  -> Retrieval Runtime
```

The builder consumes repository query results and indexes fingerprints, media
types, metadata keys, and metadata values. The runtime consumes a validated
index and never scans `KnowledgeRepository` directly.

## Models

| Model | Contents |
| --- | --- |
| `IndexEntry` | Index name, exact key, and ordered record IDs. |
| `RetrievalIndex` | Deterministic index ID, snapshot reference, records, lookup maps, and entries. |
| `RetrievalRequest` | Stable request ID and exact fingerprint, media-type, metadata-key, and metadata-value filters. |
| `RetrievalMatch` | Record ID and matched `KnowledgeRecord`. |
| `RetrievalResult` | Stable retrieval ID, request reference, ordered matches, and count. |

## Matching rules

- Fingerprint retrieval uses exact equality.
- Media-type retrieval uses exact equality.
- Metadata-key retrieval matches records containing any requested key.
- Metadata-value retrieval matches records containing any requested value.
- Combined filters use logical AND across filter categories.
- Empty filters return all indexed records in deterministic order.
- No fuzzy matching, ranking, embeddings, vector search, semantic processing,
  or AI calls are performed.

## Determinism and validation

Index IDs derive from the source snapshot and ordered index entries. Retrieval
IDs derive from the request and matched record IDs. Index maps, entries, and
runtime matches are ordered deterministically; duplicate matches, broken record
links, inconsistent indexes, and count mismatches are rejected.

## Boundary

This layer is read-only. Index construction may use `RepositoryQueryEngine`
results, while runtime execution uses only `RetrievalIndex` data. Future
retrieval systems can consume these results without adding semantic behavior to
the canonical indexed runtime.
