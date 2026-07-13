# Canonical Historical Reasoning Layer

## Purpose

Spirit 06 adds deterministic historical analysis over the canonical retrieval layer. `HistoricalReasoner` accepts a `KnowledgeRetriever` and does not access `KnowledgeGraph`, `PersistentKnowledgeRepository`, or storage files directly.

## Construction

```text
PersistentKnowledgeRepository
  → KnowledgeRetriever
  → HistoricalReasoner
```

The reasoner is read-only. It neither mutates the retrieved graph nor calls repository save or merge operations.

## API

```text
analyze_claim(claim_id)
find_related_claims(claim_id)
build_claim_cluster(claim_id)
get_support_profile(claim_id)
find_contradictions(claim_id=None)
```

## Result models

| Model | Contents |
| --- | --- |
| `ClaimCluster` | Stable cluster ID plus claim, evidence, document, and source IDs. |
| `SupportProfile` | Claim ID, evidence/source/document counts, deterministic confidence score, and confidence signals. |
| `ContradictionRecord` | Two claim IDs, a deterministic explanation, and conflict confidence. |

## Deterministic rules

Claims are related when at least one rule applies:

1. Their normalized claim text is identical. The known historical title form `The Prophet Muhammad` normalizes to `Muhammad`.
2. They share an evidence ID.
3. They share a source ID.

Clusters are transitive closures of these relationships. They group references only; no claims, evidence, or sources are merged or modified.

Support profiles count unique evidence, source, and document IDs available through `KnowledgeRetriever`. Their confidence score is a transparent capped combination of extraction confidence and those support counts; it is not fact validation.

Potential contradictions require matching normalized claim text after numeric values are replaced with `{number}`, with different extracted numeric values. For example, `Muhammad was born in 570` and `Muhammad was born in 571` form one `ContradictionRecord`.

## Compatibility boundary

`FactVerificationEngine` remains a legacy workflow compatibility component. It is not the canonical reasoning API and should not be extended for new historical analysis.

## Deferred work

This layer does not use LLMs, embeddings, semantic similarity, source ranking, factual verification, event ordering, narrative planning, or documentary planning. These require later, separately validated capabilities.
