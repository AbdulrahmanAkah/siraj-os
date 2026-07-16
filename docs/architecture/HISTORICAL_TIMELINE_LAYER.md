# Historical Timeline Layer

## Purpose

Spirit 34–35 adds a deterministic historical timeline over the canonical event
and relationship-graph outputs. It prepares chronologically ordered events for
future historical reasoning and documentary analysis without performing either
of those operations.

## Construction

```text
Event Extraction
  -> Relationship Graph
  -> Historical Timeline
```

`HistoricalTimelineArchitect` defines timeline policy. `HistoricalTimelineRuntime`
filters allowed event types, preserves explicit dates, creates entries, sorts
them, and returns a validated in-memory result.

## Models

| Model | Contents |
| --- | --- |
| `TimelineCandidate` | Pre-entry event reference and explicitly available date. |
| `TimelinePlan` | Allowed event types, undated-event policy, and validation level. |
| `TimelineEntry` | Event reference, event details, source references, and stable entry ID. |
| `HistoricalTimeline` | Ordered entries, plan reference, stable timeline ID, and count. |
| `TimelineBuildResult` | Stable result ID, validation state, timeline, and count. |

## Date and ordering rules

The runtime uses only `EventRecord.event_date` or an explicitly linked DATE
graph node whose source ID is itself a date value. Publication-date metadata is
already represented by an extracted event date. No date is inferred, estimated,
or predicted.

Dated entries sort by `event_date` ascending and then `event_id` ascending.
Undated entries are appended and sort by `event_id` ascending. Duplicate event
IDs are reduced to one deterministic entry.

## Determinism and validation

Entry IDs derive from event ID and event date. Timeline IDs derive from the plan
ID and ordered entry IDs. Result IDs derive from timeline ID and validation
state. Validation enforces unique entry/event IDs, graph-backed event references,
chronological ordering, stable output, and count consistency.

This layer performs no reasoning, narrative or documentary processing, NLP, LLM
calls, external API access, or date inference.
