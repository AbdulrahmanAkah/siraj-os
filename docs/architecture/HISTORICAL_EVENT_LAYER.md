# Canonical Historical Event Layer

## Purpose

Spirit 08 turns selected claims into deterministic historical events and orders only temporally supported events. It does not create chapters, story arcs, scenes, narration, or scripts.

## Construction

```text
Persistent Repository
  → KnowledgeRetriever
  → HistoricalReasoner
  → ClaimSelector
  → EventEngine
```

`EventEngine` accepts only `ClaimSelector`. It never reads the graph, repository, retrieval indexes, or storage directly.

## Models

| Model | Contents |
| --- | --- |
| `HistoricalEvent` | Stable event ID, title, claim/source/document/evidence IDs, confidence, optional year, and optional exact date. |
| `HistoricalTimeline` | Stable timeline ID, event objects, ordered event IDs, and unplaced event IDs. |

## Event construction

`build_event(claim_id)` obtains the claim cluster from the selector. All cluster claims become one event. The title is selected deterministically, prioritizing a claim containing an explicit event term (`battle`, `war`, `expedition`, `siege`, `migration`, or `treaty`), then selection score, then stable claim ID.

Event identity is a SHA-256-derived hash of sorted cluster claim IDs. Support references are unioned from cluster and provenance IDs. Event confidence is a capped combination of average selection score, average support confidence, and a deterministic contradiction reduction.

## Timeline rules

Temporal values are taken from explicit event/claim metadata and date/year text in selected claims.

```text
Exact date → chronological order, preferred over year-only within the same year
Year       → chronological order
Unknown    → unplaced, sorted by stable event ID
```

Exact date values support three- or four-digit historical years. Equal dates and equal years are ordered by `event_id` ascending.

There is no current claim-to-`TimelineEvent` provenance link in the canonical graph. Therefore unlinked timeline-node metadata is not inferred into events; it remains a future data-model integration concern.

## API

```text
build_event(claim_id)
build_events(limit=50)
rank_events(events=None)
build_timeline(events=None)
get_unplaced_events(events=None)
```

## Deferred work

Event construction is not event interpretation, narrative structure, chapter planning, scene planning, script generation, story arc design, or LLM event reasoning.
