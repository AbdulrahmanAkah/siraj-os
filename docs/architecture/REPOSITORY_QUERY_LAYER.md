# Canonical Repository Query Layer

## Purpose

Spirit 23 introduces the first formal query layer over the Spirit 22
knowledge repository. It provides deterministic exact retrieval by fingerprint,
media type, and metadata without semantic search, ranking, embeddings, vector
search, AI, or external access.

## Construction

```text
Knowledge Repository
  -> Repository Query Engine
  -> Future Retrieval Systems
```

`RepositoryQueryEngine` accepts only `KnowledgeRepository` and queries its
`KnowledgeRecord` or `RepositorySnapshot` values. It is read-only and does not
modify repository state.

## Models

| Model | Contents |
| --- | --- |
| `QueryRequest` | Stable query ID, exact fingerprint filters, exact media-type filters, and exact metadata filters. |
| `QueryResult` | Deterministic result ID, records ordered by `record_id`, and match count. |

## Query rules

- Fingerprints use exact equality.
- Media types use exact equality.
- Metadata filters require every requested key/value pair to match exactly.
- Multiple filter categories are combined with logical AND.
- Empty filter categories impose no restriction, allowing deterministic full
  repository queries.
- Duplicate query results are rejected.
- Results are always sorted by ascending `record_id`.
- Query and result IDs are deterministic; no UUIDs or timestamps are used.

## Snapshot querying

Queries can run against the repository's current deterministic snapshot or an
explicit validated `RepositorySnapshot`. Snapshot input is never mutated.

## Deferred work

This layer does not perform semantic retrieval, embeddings, vector search,
ranking, reasoning, claims, events, external search, or LLM operations. Those
remain future layers above exact repository querying.
