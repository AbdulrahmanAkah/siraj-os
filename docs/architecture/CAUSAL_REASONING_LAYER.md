# Causal Reasoning

## Boundary

The architect defines CAUSES, CONTRIBUTES_TO, and PRECEDES_CAUSE. The
runtime accepts only claims already referenced by historical reasoning.

## Exact extraction

A candidate is created only when the entire claim text exactly matches a
cause, canonical relation token, and effect. The claim must include
evidence. Phase 1 performs no synonym expansion, paraphrasing, semantic
matching, or causal inference. Identical relation tuples merge claim and
evidence references.

Relations are sorted by canonical tuple and assigned contiguous positions.
Candidate, relation, and result IDs are deterministic SHA-256 derivations.

Validation enforces canonical types, evidence and claim references, unique
relations, stable ordering, count consistency, and reproducible generation.
No NLP, AI, probability, or external access is allowed.
