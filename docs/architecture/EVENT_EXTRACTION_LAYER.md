# Canonical Event Extraction Layer

## Purpose

Spirit 30–31 transforms claims and entities into deterministic, traceable
events for future timeline, graph, and reasoning consumers. It defines and
executes only approved metadata, literal claim-pattern, and entity-derived
event mappings.

## Construction

```text
Claim Extraction
  -> Entity Extraction
  -> Event Extraction
  -> Future Timeline / Graph / Reasoning Consumers
```

`EventExtractionArchitect` defines the policy. `EventExtractionRuntime`
consumes `ClaimExtractionResult` and `EntityExtractionResult` through the
claim and entity runtime boundaries. It does not access repositories directly.

## Models

| Model | Contents |
| --- | --- |
| `EventCandidate` | Stable candidate ID, event type/title/date, source references, and extraction strategy. |
| `EventExtractionPlan` | Claim-result and entity-result references, canonical strategies, event limit, and validation rules. |
| `EventEvidence` | Stable evidence ID, supporting text, claim IDs, and entity IDs. |
| `EventRecord` | Stable event ID, event type/title/date, source references, and evidence. |
| `EventExtractionResult` | Stable result ID, candidates, deduplicated events, and count fields. |

## Phase 1 strategies and event types

Supported event types are `CREATION_EVENT`, `PUBLICATION_EVENT`,
`ORGANIZATION_EVENT`, `LOCATION_EVENT`, and `DATE_EVENT`.

- `METADATA_EVENT` recognizes organized fields such as `publication_date`,
  `published_at`, `created_at`, `organization`, and `location`.
- `CLAIM_PATTERN_EVENT` recognizes literal patterns such as `Published on
  2024-01-01` without inference.
- `ENTITY_DERIVED_EVENT` maps DATE, ORGANIZATION, and LOCATION entities
  directly to approved event types.

Equivalent event candidates are merged by event type, title, and date while
retaining all claim/entity references and evidence. Event IDs derive from the
event identity and ordered source references.

## Boundary and validation

Events require non-empty titles, canonical event types, at least one source
reference, and evidence. Candidate links, event links, duplicate removal,
deterministic IDs, and count consistency are validated. This layer performs no
relationship graph construction, timeline work, reasoning, narrative work, NLP,
LLM calls, or external API access.
