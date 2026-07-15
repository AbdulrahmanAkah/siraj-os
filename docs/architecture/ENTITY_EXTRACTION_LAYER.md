# Canonical Entity Extraction Layer

## Purpose

Spirit 28–29 transforms organized claims into traceable entities for future
graph and timeline consumers. `EntityExtractionArchitect` defines policy, and
`EntityExtractionRuntime` performs deterministic extraction only.

## Construction

```text
Knowledge Repository
  -> Retrieval
  -> Claim Extraction
  -> Entity Extraction
  -> Future Graph / Timeline Consumers
```

The entity layer consumes `ClaimExtractionRuntime`, `ClaimRecord`, and
`ClaimExtractionResult` contracts. It does not access repositories directly.

## Models

| Model | Contents |
| --- | --- |
| `EntityCandidate` | Stable candidate ID, source claim ID, entity name, entity type, and strategy. |
| `EntityExtractionPlan` | Claim-result reference, canonical strategies, entity limit, and validation rules. |
| `EntityEvidence` | Stable evidence ID, source claim ID, and exact supporting text. |
| `EntityRecord` | Stable entity ID, name, canonical type, source claim IDs, and evidence. |
| `EntityExtractionResult` | Stable result ID, candidates, deduplicated entities, and count fields. |

## Phase 1 strategies and types

Supported types are `PERSON`, `ORGANIZATION`, `LOCATION`, `DATE`, and `WORK`.

- `STRUCTURED_METADATA_ENTITY` recognizes deterministic fields such as
  `author`, `creator`, `publisher`, `organization`, `location`, and `date`.
- `CLAIM_PATTERN_ENTITY` recognizes exact patterns such as `Author is John
  Smith` and `Publisher is NASA`.
- `TITLE_ENTITY` copies title-derived claim text as a `WORK` entity without
  inference or paraphrasing.

Duplicate `(entity_name, entity_type)` values are merged with all source claim
IDs and evidence retained. Entity IDs derive from entity name, type, and
ordered source claim IDs.

## Boundary and validation

Entities require non-empty names, canonical types, source claims, and evidence.
Candidate links, evidence links, deterministic IDs, duplicate removal, and
count consistency are validated. This layer performs no event extraction,
relationship graph construction, timeline work, reasoning, NLP, LLM calls, or
external API access.
