# Documentary Planning Engine v2

## Boundary

Documentary Planning v2 is the first Bundle C layer. It consumes only a
valid ValidatedReasoningResult, HistoricalTimeline, RelationshipGraph, and
HistoricalInterpretationResult. Invalid reasoning is rejected before any
documentary structure is created.

## Deterministic planning

Phase 1 creates one chapter for each timeline entry that has both an
EVENT_NODE and an interpretation at the same stable position. Chapter titles
and documentary subject are copied from the first supported event title.
Scope is the sorted set of explicit event types. Time range uses only minimum
and maximum explicit event dates.

Chapter roles are positional: OPENING, CONTEXT, DEVELOPMENT, TURNING_POINT,
and OUTCOME. No creative title, subject, chapter, or prose is generated.

## Audit contract

All Bundle C models include a deterministic ID, the canonical build timestamp
1970-01-01T00:00:00Z, stable ordering metadata, and trace metadata where
applicable. The canonical timestamp is intentionally invariant; a future
execution envelope may supply real observation time without changing content
identity.

Each chapter traces source references, resolved evidence, claims, events, and
reasoning chains. The plan aggregates complete evidence coverage and trace
metadata. Validation enforces stable order, unique IDs, canonical roles,
source integrity, evidence coverage, and count consistency.

No LLM, NLP, embedding, semantic search, machine learning, external API,
probability, or undocumented heuristic is used.
