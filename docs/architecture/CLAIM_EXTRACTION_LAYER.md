# Canonical Claim Extraction Layer

## Purpose

Spirit 26–27 adds the first deterministic transformation from retrieved raw
knowledge records into traceable claims. `ClaimExtractionArchitect` defines
the extraction policy, and `ClaimExtractionRuntime` produces candidates,
evidence, and deduplicated claim records.

## Construction

```text
Knowledge Repository
  -> Repository Query
  -> Retrieval Runtime
  -> Claim Extraction
  -> Claim Repository (future)
```

The claim layer accepts only `RetrievalRuntimeEngine`, `RetrievalResult`, and
`KnowledgeRecord` contracts. It does not inspect repositories directly.

## Models

| Model | Contents |
| --- | --- |
| `ClaimCandidate` | Stable candidate ID, source record ID, exact claim text, and extraction strategy. |
| `ClaimEvidence` | Stable evidence ID, record ID, fingerprint, and exact supporting text. |
| `ClaimRecord` | Stable claim ID, exact claim text, evidence, and source record IDs. |
| `ClaimExtractionPlan` | Retrieval reference, canonical strategies, claim limit, and validation rules. |
| `ClaimExtractionResult` | Stable result ID, candidates, deduplicated claims, and count fields. |

## Phase 1 strategies

- `EXPLICIT_STATEMENT` reads only `title`, `summary`, `description`, and
  `caption` metadata fields.
- `STRUCTURED_METADATA` converts metadata pairs to deterministic statements,
  such as `Author is John Smith`.
- `TITLE_DERIVED` copies the `title` value directly without paraphrasing.

Empty values are ignored. Duplicate claim text is merged into one claim with
all source record IDs and evidence retained. Claim IDs derive from claim text
and ordered source record IDs.

## Boundary and validation

Claims require non-empty text and evidence. IDs, source links, evidence
fingerprints, duplicate claims, and result counts are validated deterministically.
The layer performs no NLP, semantic inference, entity extraction, event
extraction, relationship graph construction, reasoning, LLM calls, or external
API access.
