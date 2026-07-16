# Canonical Storyboard Architecture Layer

## Purpose

Spirit 14 converts a `ScenePlan` into a deterministic `StoryboardArchitecture`.
It defines the visual composition structure of every scene without generating
image prompts, images, video, narration, or LLM output.

## Construction

```text
Repository
  -> Retrieval
  -> Reasoning
  -> Claim Selection
  -> Event Selection
  -> Timeline
  -> Documentary Planning
  -> Narrative Architecture
  -> Script Architecture
  -> Narration Planning
  -> Scene Planning
  -> Storyboard Architecture
```

`StoryboardArchitect` accepts only `ScenePlanner`. It does not import or access
any lower layer directly and makes no AI model calls.

## Models

| Model | Contents |
| --- | --- |
| `StoryboardFrame` | Stable frame ID, source scene ID, canonical frame type, composition role, integer duration, and position. |
| `StoryboardSequence` | Stable sequence ID, source scene ID, and ordered frames for one scene. |
| `StoryboardArchitecture` | Stable architecture ID, source scene-plan ID, ordered sequences, frame count, and total duration. |

Phase 1 creates exactly one frame per scene. This satisfies the one-sequence-per-
scene and at-least-one-frame-per-scene rules while leaving multi-frame shot
distribution to a later layer.

## Mapping rules

| Scene type | Frame type | Composition role |
| --- | --- | --- |
| `HOOK_SCENE` | `ESTABLISHING` | `ORIENT` |
| `CONTEXT_SCENE` | `CONTEXTUAL` | `INFORM` |
| `EXPLANATION_SCENE` | `DETAIL` | `FOCUS` |
| `REVELATION_SCENE` | `REVEAL` | `DISCOVER` |
| `CLIMAX_SCENE` | `CLIMAX` | `PEAK` |
| `RESOLUTION_SCENE` | `TRANSITION` | `CONNECT` |
| `LEGACY_SCENE` | `CLOSING` | `REFLECT` |

## Duration distribution

Frame duration is derived from its source scene duration and has a minimum of one
second. With one frame per scene in Phase 1, each sequence's frame-duration sum
equals its scene duration, and the architecture total equals the ScenePlan total.

## Validation

A storyboard architecture is valid only when it has exactly one climax frame, at
least one establishing frame, at least one closing frame, unique IDs, complete
scene coverage, stable sequence and frame ordering, positive durations, no orphan
frames, correct type and composition mappings, and exact per-scene duration
coverage.

## Deferred work

This layer does not create shots, visual sources, image prompts, images, video,
narration, or production assets. Those remain later layers.
