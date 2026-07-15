# Evidence Resolution Layer

## Purpose

Spirit 36–37 adds the canonical deterministic evidence layer. It gathers
traceable evidence from claims, entities, events, relationship-graph edges, and
historical-timeline entries into resolved evidence records and source bundles.

## Construction

```text
Claims -> Entities -> Events -> Relationship Graph -> Historical Timeline
  -> Evidence Resolution
```

`EvidenceResolutionArchitect` defines permitted source types and validation
level. `EvidenceResolutionRuntime` collects evidence, merges exact duplicates,
creates deterministic bundles, and returns a validated in-memory result.

## Models

| Model | Contents |
| --- | --- |
| `EvidenceReference` | Stable reference ID, evidence ID, source type, and source ID. |
| `EvidenceBundle` | Stable bundle ID, resolved evidence IDs, and ordered references. |
| `EvidenceResolutionPlan` | Allowed canonical source types and validation level. |
| `ResolvedEvidence` | Exact evidence text, merged references, source types, and stable ID. |
| `EvidenceResolutionResult` | Ordered resolved evidence, bundles, counts, validation state, and stable ID. |

## Exact resolution rules

Evidence is identical only when its text and deterministic source-content key
are both equal. No fuzzy or semantic matching, embeddings, or source
correlation is performed. Exact duplicates merge references and source types;
all references and source types are sorted deterministically.

Graph-edge evidence uses the explicit edge type and endpoints. Timeline-entry
evidence uses the explicit title and event/source references. These structural
representations do not infer additional facts.

## Determinism and boundary

Resolved evidence IDs derive from evidence text and ordered references. Bundle
IDs derive from ordered resolved evidence IDs. Result IDs derive from ordered
resolved evidence IDs and validation state. Validation enforces unique IDs and
references, valid source linkage, count consistency, and stable ordering.

This layer performs no multi-source correlation, consistency or contradiction
analysis, reasoning, narrative processing, NLP, LLM calls, or external access.
