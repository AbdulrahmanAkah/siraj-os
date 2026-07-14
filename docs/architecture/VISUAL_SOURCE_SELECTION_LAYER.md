# Canonical Visual Source Selection Layer

## Purpose

Spirit 16 converts a `VisualAssetArchitecture` into a deterministic
`VisualSourcePlan`. It determines the source categories required for each visual
asset without downloading, scraping, searching the web, generating media, or
invoking AI models.

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
  -> Visual Source Selection
```

`VisualSourceSelector` accepts only `VisualAssetArchitect`. It does not import or
access any lower layer directly and makes no web, API, or AI calls.

## Models

| Model | Contents |
| --- | --- |
| `VisualSource` | Stable source ID, source visual-asset ID, canonical source type, source priority, and position. |
| `SourceBundle` | Stable bundle ID, source asset-group ID, and ordered sources for one asset group. |
| `VisualSourcePlan` | Stable plan ID, source visual-asset-architecture ID, ordered bundles, and source count. |

Phase 1 creates exactly one source-category requirement per visual asset. This
satisfies the one-bundle-per-group and at-least-one-source-per-asset rules while
leaving real source discovery and evidence collection to later layers.

## Mapping rules

| Asset type | Source type | Source priority |
| --- | --- | --- |
| `HISTORICAL_PERSON` | `ARCHIVE_PHOTOGRAPH` | `MANDATORY` |
| `HISTORICAL_LOCATION` | `MUSEUM_COLLECTION` | `MANDATORY` |
| `HISTORICAL_OBJECT` | `MUSEUM_COLLECTION` | `PREFERRED` |
| `DOCUMENT` | `HISTORICAL_DOCUMENT` | `MANDATORY` |
| `MAP` | `MAP_ARCHIVE` | `PREFERRED` |
| `TIMELINE_GRAPHIC` | `TIMELINE_ASSET` | `OPTIONAL` |
| `ARTWORK` | `ART_RECONSTRUCTION` | `OPTIONAL` |

`ACADEMIC_SOURCE` remains a canonical source-type vocabulary item, but the
specified Phase 1 asset mappings do not assign it to an asset type. Academic
source discovery is therefore deferred until a future mapping rule is defined.

## Validation

A source plan is valid only when it has at least one mandatory source, unique
source and bundle IDs, complete asset coverage, no orphan sources, stable bundle
and source ordering, valid source-to-asset links, and valid bundle-to-group
links.

## Deferred work

This layer does not discover actual URLs, download materials, scrape websites,
search the web, call external APIs, verify sources, or generate media. Those
remain later layers.
