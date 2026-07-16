# Provenance and Evidence Foundation

## Claim lifecycle

```text
Source → DocumentReference → EvidenceReference → Claim → KnowledgeGraph
```

`KnowledgeRepository` assigns deterministic IDs while mapping canonical extractor output. For each imported document it creates a `DocumentReference`; for every extracted claim it creates an `EvidenceReference` and a `ClaimEvidence` link. Extractor confidence is carried through unchanged and is recorded, not interpreted.

## Canonical provenance models

| Model | Location | Purpose |
| --- | --- | --- |
| `DocumentReference` | `src.domain.knowledge_objects.document_reference` | Stable document ID, title, and originating source ID. |
| `EvidenceReference` | `src.domain.knowledge_objects.evidence_reference` | Stable passage ID, document ID, paragraph/sentence coordinates, and text. |
| `ClaimEvidence` | `src.domain.knowledge_objects.claim_evidence` | Claim-to-evidence support link and recorded confidence. |

The canonical `Claim` now carries `claim_id`, `source_ids`, `evidence_ids`, and `confidence`. The canonical `Source` now carries `source_id`; direct construction derives a deterministic ID from its title, URL, and type when one is not supplied. All fields have defaults, preserving existing callers.

## Graph representation

The existing canonical graph model is unchanged. `GraphBuilder` serializes provenance as ordinary nodes and edges:

```text
CLAIM --supported_by--> EVIDENCE --located_in--> DOCUMENT --originates_from--> SOURCE
CLAIM --attributed_to--> SOURCE
```

`KnowledgeNode.data` contains the complete dataclass payload and `KnowledgeEdge.metadata` stores recorded confidence. `KnowledgeGraph.to_dict()` therefore preserves provenance through JSON serialization without a parallel graph format.

## Boundaries and future extension points

This foundation records extraction provenance only. It does not judge source quality, validate facts, rank claims, retrieve documents, detect contradictions, order events, or plan narrative. Future retrieval can attach document locators; verification and reasoning can add assessments to `ClaimEvidence` without replacing claim identity or graph links.
