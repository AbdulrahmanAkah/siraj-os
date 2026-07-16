# Canonical Source Acquisition Planning Layer

## Purpose

Spirit 18 converts a `SourceDiscoveryPlan` into a deterministic
`SourceAcquisitionPlan`. It defines how discovered source categories should be
acquired, prioritized, verified, and prepared for ingestion without downloads,
API calls, scraping, crawling, web access, or AI operations.

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
  -> Source Acquisition Planning
```

`SourceAcquisitionPlanner` accepts only `SourceDiscoveryArchitect`. It does not
import or access any lower layer directly and makes no external calls.

## Models

| Model | Contents |
| --- | --- |
| `AcquisitionTarget` | Stable target ID, source-discovery query ID, acquisition method, verification requirement, priority, and position. |
| `AcquisitionBatch` | Stable batch ID, discovery-bundle ID, and ordered acquisition targets. |
| `SourceAcquisitionPlan` | Stable plan ID, source-discovery-plan ID, ordered batches, and target count. |

Phase 1 creates exactly one acquisition target per discovery query and exactly
one acquisition batch per discovery bundle. These are planning specifications;
they do not acquire or retrieve sources.

## Mapping rules

| Discovery channel | Acquisition method | Verification | Priority |
| --- | --- | --- | --- |
| `PUBLIC_ARCHIVE` | `ARCHIVE_REQUEST` | `STRICT_VERIFICATION` | `CRITICAL` |
| `MUSEUM_CATALOG` | `CATALOG_LOOKUP` | `STRICT_VERIFICATION` | `HIGH` |
| `LIBRARY_CATALOG` | `DOCUMENT_RETRIEVAL` | `STRICT_VERIFICATION` | `HIGH` |
| `MAP_REPOSITORY` | `MAP_RETRIEVAL` | `STANDARD_VERIFICATION` | `MEDIUM` |
| `ACADEMIC_INDEX` | `ACADEMIC_LOOKUP` | `STRICT_VERIFICATION` | `HIGH` |
| `ART_COLLECTION` | `COLLECTION_REVIEW` | `STANDARD_VERIFICATION` | `LOW` |
| `INTERNAL_ASSET_LIBRARY` | `INTERNAL_FETCH` | `BASIC_VERIFICATION` | `LOW` |

## Validation

An acquisition plan is valid only when it has at least one critical target,
unique target and batch IDs, complete query coverage, exactly one target per
query, no orphan targets, stable ordering, and only canonical acquisition
methods, verification requirements, and priority levels.

## Deferred work

This layer does not download, crawl, scrape, call APIs or HTTP endpoints,
retrieve sources, prepare files, or invoke AI. Actual acquisition remains a
future execution layer.
