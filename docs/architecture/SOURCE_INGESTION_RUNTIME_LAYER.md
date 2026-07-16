# Canonical Source Ingestion Runtime Layer

## Purpose

Spirit 20 transforms a `SourceIngestionPlan` into deterministic execution
results over local in-memory payloads. It performs normalization,
fingerprinting, deduplication decisions, validation, and reporting without
network access, repository mutation, database writes, OCR, media generation,
or AI operations.

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
  -> Source Ingestion Runtime
```

`SourceIngestionExecutor` accepts only `SourceIngestionArchitect`. It does not
import or access any lower layer and operates only on an explicit plan plus a
caller-provided mapping of acquisition-target IDs to in-memory payloads.

## Runtime models

| Model | Contents |
| --- | --- |
| `IngestionPayload` | Acquisition-target ID, raw bytes, media type, and string metadata. |
| `NormalizedPayload` | Unit ID, preserved bytes, normalized media type, and normalized metadata. |
| `FingerprintResult` | Unit ID, deterministic fingerprint, and fingerprint strategy. |
| `DeduplicationResult` | Unit ID, fingerprint, duplicate decision, and first accepted duplicate source. |
| `ValidationResult` | Unit ID, validity, validation level, and canonical error codes. |
| `IngestionExecutionResult` | Stable execution ID, ordered runtime artifacts, and processed/accepted/rejected/duplicate counters. |

## Execution behavior

Units execute in stable ingestion-plan order. Missing payloads produce one
invalid validation result with `MISSING_PAYLOAD` and no normalization,
fingerprint, or deduplication result. Valid non-duplicates are accepted; valid
duplicates point to the first earlier accepted unit and are counted separately.

Normalization preserves bytes and only canonicalizes metadata keys/values and
media-type casing. It performs no decoding, transcoding, resizing, OCR, parsing,
image manipulation, or document extraction.

## Fingerprints

- `SHA256_FINGERPRINT` hashes normalized bytes.
- `METADATA_FINGERPRINT` hashes stable sorted JSON metadata serialization.
- `PERCEPTUAL_FINGERPRINT` is a deterministic Phase 1 placeholder that hashes
  normalized media type, a separator, and normalized bytes; it is not a true
  perceptual hash.

All deduplication policies use exact fingerprint equality in Phase 1 while
preserving the policy in the ingestion unit for future policy-specific logic.

## Validation and determinism

Runtime plans must pass `SourceIngestionArchitect` validation. Payload mapping
keys must be acquisition-target IDs and each payload's `target_id` must match
its key. Invalid runtime mappings raise `ValueError`; missing payloads are
handled as ordinary deterministic execution results.

Execution IDs derive from the plan ID, ordered unit IDs, payload target IDs,
fingerprints, validation states/errors, and duplicate decisions. No random IDs,
network calls, repository writes, database writes, or external retrieval occur.

## Deferred work

This layer does not persist accepted materials, ingest repositories, parse files,
run OCR, generate media, or invoke AI. Those remain future execution layers.
