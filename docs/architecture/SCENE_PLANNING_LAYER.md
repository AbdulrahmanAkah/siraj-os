# Canonical Scene Planning Layer

## Purpose

Spirit 13 converts a `NarrationPlan` into a deterministic `ScenePlan`. It defines
the visual structure of the documentary without generating images, image prompts,
narration text, video, or storyboard content.

## Construction

```text
Persistent Repository
  -> KnowledgeRetriever
  -> HistoricalReasoner
  -> ClaimSelector
  -> EventEngine
  -> DocumentaryPlanner
  -> NarrativeArchitect
  -> ScriptArchitect
  -> NarrationPlanner
  -> ScenePlanner
```

`ScenePlanner` accepts only `NarrationPlanner`. It does not import or access any
lower layer directly and makes no AI model calls.

## Models

| Model | Contents |
| --- | --- |
| `Scene` | Stable scene ID, source narration block ID, canonical scene type, visual role, integer duration, and position. |
| `ScenePlan` | Stable plan ID, source narration plan ID, ordered scenes, total duration, and scene count. |

Exactly one scene is generated for each narration block. Scene order follows the
narration block position and stable block ID.

## Mapping rules

| Narration role | Scene type | Visual role |
| --- | --- | --- |
| `HOOK` | `HOOK_SCENE` | `ATTENTION` |
| `CONTEXT` | `CONTEXT_SCENE` | `ORIENTATION` |
| `EXPLANATION` | `EXPLANATION_SCENE` | `EXPLANATION` |
| `REVELATION` | `REVELATION_SCENE` | `DISCOVERY` |
| `CLIMAX_NARRATION` | `CLIMAX_SCENE` | `PEAK` |
| `RESOLUTION` | `RESOLUTION_SCENE` | `AFTERMATH` |
| `LEGACY_REFLECTION` | `LEGACY_SCENE` | `REFLECTION` |

## Duration estimation

Duration is calculated from `NarrationBlock.estimated_word_count` at a fixed rate
of 150 words per minute, rounded up to an integer number of seconds. Each scene
has a minimum duration of 2 seconds and a maximum duration of 30 seconds.

## Validation

A scene plan is valid only when it has exactly one hook scene, exactly one climax
scene, at least one resolution or legacy scene, unique scene IDs, one scene for
each narration block, contiguous stable positions, positive bounded durations,
correct role mappings, consistent totals, and full narration coverage.

## Deferred work

This layer does not create image prompts, storyboards, visual assets, narration,
video, or production scenes. Those are later layers.
