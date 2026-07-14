# Canonical Source Ingestion Architecture Layer

## Purpose

Spirit 19 converts a `SourceAcquisitionPlan` into a deterministic
`SourceIngestionPlan`. It defines how acquired materials will be normalized,
validated, fingerprinted, deduplicated, and prepared for repository insertion
without parsing real files, OCR, AI inference, database writes, or repository
mutation.

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
  -> Source Ingestion Architecture
```

`SourceIngestionArchitect` accepts only `SourceAcquisitionPlanner`. It does not
import or access any lower layer directly and makes no external calls.

## Models

| Model | Contents |
| --- | --- |
| `IngestionUnit` | Stable unit ID, acquisition-target ID, normalization strategy, fingerprint strategy, deduplication policy, validation level, and position. |
| `IngestionBatch` | Stable ingestion-batch ID, acquisition-batch ID, and ordered ingestion units. |
| `SourceIngestionPlan` | Stable plan ID, source-acquisition-plan ID, ordered batches, and unit count. |

Phase 1 creates exactly one ingestion unit per acquisition target and exactly
one ingestion batch per acquisition batch. These are preparation specifications;
they do not parse, ingest, or mutate repository data.

## Mapping rules

| Acquisition method | Normalization | Fingerprint | Deduplication | Validation |
| --- | --- | --- | --- | --- |
| `ARCHIVE_REQUEST` | `ARCHIVE_NORMALIZATION` | `SHA256_FINGERPRINT` | `STRICT_DEDUPLICATION` | `STRICT` |
| `CATALOG_LOOKUP` | `METADATA_NORMALIZATION` | `METADATA_FINGERPRINT` | `STANDARD_DEDUPLICATION` | `STANDARD` |
| `DOCUMENT_RETRIEVAL` | `DOCUMENT_NORMALIZATION` | `SHA256_FINGERPRINT` | `STRICT_DEDUPLICATION` | `STRICT` |
| `MAP_RETRIEVAL` | `MAP_NORMALIZATION` | `PERCEPTUAL_FINGERPRINT` | `STANDARD_DEDUPLICATION` | `STANDARD` |
| `ACADEMIC_LOOKUP` | `DOCUMENT_NORMALIZATION` | `SHA256_FINGERPRINT` | `STRICT_DEDUPLICATION` | `STRICT` |
| `COLLECTION_REVIEW` | `IMAGE_NORMALIZATION` | `PERCEPTUAL_FINGERPRINT` | `RELAXED_DEDUPLICATION` | `BASIC` |
| `INTERNAL_FETCH` | `METADATA_NORMALIZATION` | `METADATA_FINGERPRINT` | `STANDARD_DEDUPLICATION` | `BASIC` |

## Validation

An ingestion plan is valid only when it has at least one strict validation
unit, unique unit and batch IDs, complete acquisition-target coverage, exactly
one unit per target, no orphan units, stable ordering, and only canonical
normalization, fingerprint, deduplication, and validation values.

## Deferred work

This layer does not parse files, run OCR, fingerprint actual bytes, deduplicate
real materials, write databases, mutate repositories, ingest sources, or invoke
AI. Those remain future execution layers.
