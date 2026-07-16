# Canonical Source Discovery Architecture Layer

## Purpose

Spirit 17 converts a `VisualSourcePlan` into a deterministic
`SourceDiscoveryPlan`. It defines where and how visual source categories should
be discovered in the future without performing network activity, downloads,
scraping, API calls, AI calls, or source retrieval.

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
  -> Source Discovery Architecture
```

`SourceDiscoveryArchitect` accepts only `VisualSourceSelector`. It does not
import or access any lower layer directly and makes no external calls.

## Models

| Model | Contents |
| --- | --- |
| `DiscoveryQuery` | Stable query ID, source ID, discovery channel, query strategy, verification level, and position. |
| `DiscoveryBundle` | Stable discovery-bundle ID, source-bundle ID, and ordered discovery queries. |
| `SourceDiscoveryPlan` | Stable plan ID, source-plan ID, ordered discovery bundles, and query count. |

Phase 1 creates exactly one discovery query per visual source and exactly one
discovery bundle per source bundle. These are specifications only; they do not
contain real search text or perform source discovery.

## Mapping rules

| Source type | Discovery channel | Query strategy | Verification |
| --- | --- | --- | --- |
| `ARCHIVE_PHOTOGRAPH` | `PUBLIC_ARCHIVE` | `ENTITY_AND_DATE` | `STRICT` |
| `MUSEUM_COLLECTION` | `MUSEUM_CATALOG` | `ENTITY_AND_LOCATION` | `STRICT` |
| `HISTORICAL_DOCUMENT` | `LIBRARY_CATALOG` | `DOCUMENT_TITLE` | `STRICT` |
| `MAP_ARCHIVE` | `MAP_REPOSITORY` | `ENTITY_AND_LOCATION` | `STANDARD` |
| `ACADEMIC_SOURCE` | `ACADEMIC_INDEX` | `SUBJECT_SEARCH` | `STRICT` |
| `ART_RECONSTRUCTION` | `ART_COLLECTION` | `COLLECTION_BROWSE` | `STANDARD` |
| `TIMELINE_ASSET` | `INTERNAL_ASSET_LIBRARY` | `METADATA_FILTER` | `BASIC` |

## Validation

A source-discovery plan is valid only when it has at least one strict query,
unique query and bundle IDs, complete source coverage, exactly one query per
source, no orphan queries, stable ordering, valid source references, and only
canonical channels, strategies, and verification levels.

## Deferred work

This layer does not generate real queries, search the web, call APIs, download
or scrape content, retrieve sources, verify external materials, or invoke AI.
Those remain outside the architecture phase.
