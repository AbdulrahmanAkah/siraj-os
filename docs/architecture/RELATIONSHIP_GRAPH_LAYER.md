# Canonical Relationship Graph Layer

## Purpose

Spirit 32–33 adds the first deterministic knowledge graph that connects
claims, entities, and events with traceable relationship edges. The graph is
an in-memory structural result for future timeline and reasoning consumers.

## Construction

```text
Claim Extraction
  -> Entity Extraction
  -> Event Extraction
  -> Relationship Graph
```

`RelationshipGraphArchitect` defines the graph boundary, and
`RelationshipGraphRuntime` creates nodes and edges from claim, entity, and
event extraction results. It does not access repositories directly.

## Models

| Model | Contents |
| --- | --- |
| `GraphNode` | Deterministic node ID, canonical node type, and source ID. |
| `GraphEdge` | Deterministic edge ID, canonical edge type, and source/target node IDs. |
| `RelationshipCandidate` | Deterministic edge candidate before duplicate removal. |
| `RelationshipGraph` | Graph identity, source-result references, ordered nodes/edges, and counts. |
| `RelationshipGraphResult` | Stable result ID, graph, candidates, and count fields. |

## Node and edge rules

Nodes use `CLAIM_NODE`, `ENTITY_NODE`, and `EVENT_NODE`. Edges use
`REFERENCES` for claim-to-entity links, `SUPPORTED_BY` for event-to-claim
links, and `ASSOCIATED_WITH` for event-to-entity links. Location entities add
`LOCATED_IN` edges and date entities add `OCCURRED_ON` edges.

Node IDs derive from node type and source ID. Edge IDs derive from edge type,
source node ID, and target node ID. Duplicate nodes and edges are removed
deterministically.

## Validation and boundary

Validation enforces canonical types, unique IDs, existing node references,
source-result linkage, stable ordering, and count consistency. This layer does
not perform timeline construction, reasoning, narrative processing, NLP, LLM
calls, or external API access.
