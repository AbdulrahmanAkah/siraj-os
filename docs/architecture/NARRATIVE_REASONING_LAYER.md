# Narrative Reasoning

## Boundary

This layer labels supported, ordered events without creative generation.
Only timeline events represented by a historical reasoning chain are used.

The first eligible event is BEGINNING, the last is OUTCOME, the central
interior event is TURNING_POINT, and remaining interior events are
DEVELOPMENT. A single event is BEGINNING.

Every record preserves event ID, reasoning chain ID, evidence IDs, and its
contiguous timeline-derived position. IDs are deterministic.

Validation enforces canonical roles, source event and chain integrity,
evidence presence, unique IDs, stable ordering, and count consistency. The
runtime does not invent narrative facts, prose, motives, or causal links.
