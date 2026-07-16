# Historical Reasoning Foundation

## Boundary

This layer creates traceable reasoning chains from HistoricalTimeline,
RelationshipGraph, EvidenceResolutionResult, and KnowledgeConfidenceResult.
It does not infer facts or create prose.

The architect emits a deterministic HistoricalReasoningPlan. The runtime
emits one chain for each eligible timeline event. An event is eligible only
when it has an EVENT_NODE and at least one resolved-evidence reference to
the event, timeline entry, source claim, or source entity.

## Trace contract

Each candidate preserves its event ID, graph node ID, resolved evidence IDs,
confidence IDs when available, source claim IDs, source entity IDs, and
timeline position. A chain contains exactly one candidate in phase 1.

IDs are SHA-256-derived from canonical input material. Timeline order is
preserved. Missing graph or evidence support excludes a candidate.

## Validation and exclusions

Validation enforces unique IDs, count consistency, stable ordering, valid
graph links, evidence links, and chain/candidate agreement. This layer uses
no probability, NLP, LLM, external API, or semantic matching.
