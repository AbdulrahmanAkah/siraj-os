# Canonical Visual Asset Architecture Layer

## Purpose

Spirit 15 converts a `StoryboardArchitecture` into a deterministic
`VisualAssetArchitecture`. It defines which visual asset categories are required
for the documentary without generating prompts, images, video, narration, or AI
output.

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
  -> Visual Asset Architecture
```

`VisualAssetArchitect` accepts only `StoryboardArchitect`. It does not import or
access any lower layer directly and makes no web or AI calls.

## Models

| Model | Contents |
| --- | --- |
| `VisualAsset` | Stable asset ID, source frame ID, canonical asset type, asset role, priority, and position. |
| `AssetGroup` | Stable group ID, source sequence ID, and ordered assets for one storyboard sequence. |
| `VisualAssetArchitecture` | Stable architecture ID, source storyboard-architecture ID, ordered asset groups, and asset count. |

Phase 1 creates exactly one asset requirement per storyboard frame. This
satisfies the one-group-per-sequence and at-least-one-asset-per-frame rules while
leaving multiple-source and asset-variant selection to later layers.

## Mapping rules

| Frame type | Asset type | Asset role | Priority |
| --- | --- | --- | --- |
| `ESTABLISHING` | `HISTORICAL_LOCATION` | `PRIMARY` | `CRITICAL` |
| `CONTEXTUAL` | `MAP` | `CONTEXT` | `HIGH` |
| `DETAIL` | `HISTORICAL_OBJECT` | `SUPPORTING` | `MEDIUM` |
| `REVEAL` | `DOCUMENT` | `EVIDENCE` | `HIGH` |
| `CLIMAX` | `HISTORICAL_PERSON` | `PRIMARY` | `CRITICAL` |
| `TRANSITION` | `TIMELINE_GRAPHIC` | `TRANSITION` | `MEDIUM` |
| `CLOSING` | `ARTWORK` | `CONTEXT` | `LOW` |

## Validation

A visual asset architecture is valid only when it has at least one critical
asset, at least one primary asset, unique asset and group IDs, complete frame
coverage, no orphan assets, stable ordering, valid group-to-sequence links, and
correct type, role, and priority mappings.

## Deferred work

This layer does not select actual sources, download materials, create image
prompts, generate images, produce video, or invoke AI. Those remain later layers.
