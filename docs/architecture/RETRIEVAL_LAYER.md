# Canonical Retrieval Layer

## Purpose

Spirit 05 introduces a read-only query boundary over a loaded canonical knowledge graph. Future retrieval consumers should use `KnowledgeRetriever` instead of directly accessing `KnowledgeGraph.nodes`, `KnowledgeGraph.edges`, or graph indexes.

## Construction

```text
PersistentKnowledgeRepository.load()
  → KnowledgeRetriever.from_repository(repository)
  → RetrievalIndex
```

`KnowledgeRetriever.load_repository(path)` is available when only a repository path is known. Neither construction path modifies the graph or storage.

## Indexes

`RetrievalIndex` is built once for each retriever and contains:

- `nodes_by_id`
- `edges_by_id`
- `claims_by_id`
- `sources_by_id`
- `documents_by_id`
- `evidence_by_id`
- `nodes_by_type`
- `outgoing_by_node_id`
- `incoming_by_node_id`

Stable-ID lookup is dictionary-backed and therefore O(1) on the loaded graph.

## API

```text
find_node(node_id)
find_claim(claim_id)
find_source(source_id)
find_document(document_id)
find_evidence(evidence_id)
find_entities(name)
find_entity(name)
find_people(name)
find_locations(name)
find_events(name)
get_incoming(node_id)
get_outgoing(node_id)
get_neighbors(node_id)
get_relationships(node_id)
get_claim_evidence(claim_id)
get_claim_sources(claim_id)
get_evidence_document(evidence_id)
get_document_source(document_id)
get_claim_provenance(claim_id)
```

Name-based entity helpers are convenience discovery methods. Canonical object retrieval and traversal use stable IDs.

## Provenance

`get_claim_provenance(claim_id)` returns a dictionary containing the claim, its evidence, documents, and sources. The implementation follows the persisted graph path:

```text
Claim → Evidence → Document → Source
```

It first uses provenance IDs stored in canonical node data and falls back to the corresponding graph edges for compatibility with older persisted graphs.

## Boundary

The retrieval layer is read-only. It does not call repository `save()` or `merge()`, mutate graph nodes/edges, rank results, search semantically, use embeddings, or invoke an LLM.

`application.knowledge.graph_query.GraphQuery` and `domain.knowledge_graph.knowledge_graph_query.KnowledgeGraphQuery` remain legacy direct-graph helpers and are not the canonical API for new work.

## Deferred work

Text search, ranking, semantic retrieval, embeddings, vector stores, RAG, and fact validation are deferred to later Spirits. Deterministic historical analysis is provided by `HistoricalReasoner` in the separate reasoning layer.
