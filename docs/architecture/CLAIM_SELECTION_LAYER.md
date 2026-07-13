# Canonical Claim Selection Layer

## Purpose

Spirit 07 adds deterministic, explainable claim selection above historical reasoning. New planning consumers should receive selected claims from `ClaimSelector`, not enumerate all repository claims directly.

## Construction

```text
Persistent Repository
  → KnowledgeRetriever
  → HistoricalReasoner
  → ClaimSelector
```

`ClaimSelector` accepts only `HistoricalReasoner`. It does not access `KnowledgeGraph`, storage, or `KnowledgeRetriever` directly, and it does not modify any persisted knowledge.

## API

```text
evaluate_claim(claim_id)
rank_claims()
select_top_claims(limit=50)
select_claims(limit=50)
reject_claims()
build_selection_profile(claim_id)
```

## Result models

| Model | Contents |
| --- | --- |
| `ClaimScore` | Claim ID, final score, support/source/evidence components, and contradiction penalty. |
| `SelectionProfile` | Claim ID, final score, deterministic reasons, support summary, and contradiction summary. |

## Deterministic score

The selector combines only reasoning outputs:

```text
support_score       = support_profile.confidence_score × 0.30
source_score        = min(source_count, 2) × 0.125
evidence_score      = min(evidence_count, 2) × 0.125
cluster_bonus       = min(related_claim_count - 1, 3) × 0.03
contradiction_penalty = min(conflict_count × 0.30, 0.50)
final_score         = max(0, support + source + evidence + cluster_bonus - penalty)
```

Scores are rounded to three decimal places. Ranking is descending by final score and then ascending by stable claim ID, making repeated results deterministic.

Claims below `0.35` are returned by `reject_claims()`. Selection does not delete, merge, or otherwise alter rejected claims.

## Explainability

`build_selection_profile(claim_id)` records each component contribution, cluster bonus when applicable, contradiction penalty when applicable, support counts, and the potential contradiction count. The profile explains selection without relying on an LLM or opaque ranking model.

## Deferred work

Selection is not narrative planning, event ordering, story construction, scene planning, semantic ranking, embeddings, or LLM scoring. Those capabilities remain separate future concerns.
