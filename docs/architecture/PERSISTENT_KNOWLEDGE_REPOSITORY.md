# Persistent Knowledge Repository

## Purpose

Spirit 04 makes the canonical knowledge graph durable across processes. Persistence is an application-layer concern; it does not introduce a second domain graph or a retrieval system.

## Runtime flow

```text
Load persistent graph
  → extract and build canonical incoming graph
  → merge by stable node and relationship IDs
  → save repository snapshot
  → generate documentary artifacts from the merged graph
```

`DocumentaryWorkflow` enables this flow only when a `repository_path` is supplied. Existing callers without a repository path retain the in-memory workflow behavior.

## Storage format

The repository directory contains one canonical snapshot and typed inspection projections:

```text
repository/
├── graph.json       # canonical nodes, edges, and graph relationships
├── sources.json     # SOURCE-node projection
├── documents.json   # DOCUMENT-node projection
├── evidence.json    # EVIDENCE-node projection
├── claims.json      # CLAIM-node projection
└── metadata.json    # schema version and counts
```

`graph.json` is authoritative for rehydration. The typed files are generated from it and exist for inspection, migration, and future repository tooling.

## Identity and merge rules

- Source IDs derive from title, URL, and type.
- Document IDs derive from sanitized document content.
- Claim IDs derive from normalized claim text.
- Evidence IDs derive from document ID, sentence position, and evidence text.
- Graph node IDs are canonical object IDs; statistics and timeline nodes use deterministic content IDs.
- `KnowledgeEdge.relationship_id` derives from source, target, relation, and metadata.

During merge, nodes with identical IDs become one node. Dictionary payloads merge recursively and list values are unioned, preserving additional source/evidence references. Edges with identical relationship IDs become one edge.

## Public application boundary

`PersistentKnowledgeRepository` provides:

- `load()`
- `save(graph)`
- `merge(graph)`
- `exists(object_id=None)`
- `get_by_id(object_id)`

CLI usage:

```text
python -m src.cli.generate Muhammad test_source.txt --repository data/repository
```

## Deferred capabilities

This repository provides persistence and identity-based merge only. Retrieval, ranking, embeddings, vector storage, reasoning, contradiction detection, and source evaluation remain out of scope.
