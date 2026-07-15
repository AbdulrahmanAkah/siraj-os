# Reasoning Validation

## Boundary

The final Bundle B gate validates reasoning and interpretation without
repairing them. Its plan always runs five checks in canonical order:

1. EVIDENCE_COMPLETENESS
2. REFERENCE_INTEGRITY
3. TIMELINE_CONSISTENCY
4. GRAPH_CONSISTENCY
5. CONTRADICTION_CONFLICTS

Each check records a deterministic ID, pass state, canonical error codes,
inspected or conflicting references, and position.

Reference integrity verifies chains, resolved evidence, and original
evidence references. Timeline consistency verifies unique events and
date/event ordering. Graph consistency verifies every edge and reasoning
node. Contradictions fail only when their claim IDs intersect claims used by
reasoning.

The result is VALID only when every check passes. IDs include the plan,
reasoning, interpretation, ordered checks, and validation state. No
inference, correction, AI, NLP, or external service is used.
