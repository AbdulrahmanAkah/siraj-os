# Canonical Documentary Planning Layer

## Purpose

Spirit 09 deterministically converts an `HistoricalTimeline` into an auditable documentary structure. It produces sections and runtime estimates; it does not generate prose, scenes, narration, images, or directing decisions.

## Construction

```text
Persistent Repository
  -> KnowledgeRetriever
  -> HistoricalReasoner
  -> ClaimSelector
  -> EventEngine
  -> DocumentaryPlanner
```

`DocumentaryPlanner` accepts only `EventEngine`. It has no repository, graph, claim, retrieval, or reasoning dependency. It is read-only.

## Models

| Model | Contents |
| --- | --- |
| `DocumentarySection` | Stable section ID, title, assigned event IDs, deterministic importance, and estimated duration in minutes. |
| `DocumentaryPlan` | Stable plan ID, title, ordered sections, selected event IDs, and total estimated runtime in minutes. |

## Planning rules

- The introduction selects the highest deterministic event-importance score, then event ID.
- Importance is `70%` event confidence plus `30%` bounded support strength derived from claim, evidence, and source counts.
- The conclusion prioritizes remaining events with explicit outcome/legacy-impact terms, then the latest timeline event. Equal positions resolve by importance, then event ID.
- Remaining events retain timeline order and are distributed as evenly as possible across at most three numbered chapters.
- Each event is assigned exactly once.
- A non-empty section estimates `1.0 + 0.75 * event_count` minutes. Plan runtime is the sum of its sections.
- Plan identity is a SHA-256-derived hash of its title and ordered event IDs.

## API

```text
build_documentary_plan(timeline=None, title=None)
build_sections(timeline=None)
rank_sections(sections=None, timeline=None)
estimate_runtime(sections=None, timeline=None)
assign_event(event_id, timeline=None)
get_introduction(timeline=None)
get_conclusion(timeline=None)
```

## Deferred work

This is not script writing, narration, scene planning, image prompt creation, story-arc interpretation, director decisions, or LLM storytelling. The existing production workflow remains unchanged until a later, separately tested integration spirit adopts this canonical plan.
