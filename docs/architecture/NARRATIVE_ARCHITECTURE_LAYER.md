# Canonical Narrative Architecture Layer

## Purpose

Spirit 10 converts a DocumentaryPlan into a deterministic narrative architecture. It decides the structural role and order of beats without writing narration, scripts, scenes, or image prompts.

## Construction

Persistent Repository
  -> KnowledgeRetriever
  -> HistoricalReasoner
  -> ClaimSelector
  -> EventEngine
  -> DocumentaryPlanner
  -> NarrativeArchitect

NarrativeArchitect accepts only DocumentaryPlanner. It does not import or access the repository, graph, retrieval, reasoner, selector, or event engine directly.

## Models

| Model | Contents |
| --- | --- |
| NarrativeBeat | Stable beat ID, title, section ID, event IDs, canonical beat type, importance, and position. |
| NarrativeArc | Stable arc ID, title, ordered beat IDs, and average importance. |
| NarrativeArchitecture | Stable architecture ID, documentary plan ID, beats, arcs, and deterministic complexity level. |

## Beat rules

- Introduction: SETUP and CONTEXT.
- Middle section with the highest importance: exactly one CLIMAX; ties use section ID.
- Other middle sections: ESCALATION before the climax and TURNING_POINT after it.
- Conclusion: AFTERMATH and LEGACY.
- For a minimal plan without middle or conclusion sections, the introduction/last section receives the missing climax and end beats so the same validation invariant holds.

## Arcs and complexity

- Beginning: setup and context beats.
- Middle: escalation, turning-point, and climax beats.
- End: aftermath and legacy beats.
- Complexity is LOW at a combined section/event/beat count of 7 or less, MEDIUM through 14, and HIGH above 14.

## Validation

An architecture is valid only when it has exactly one climax, at least one setup beat, at least one end beat, unique beat IDs, valid section references, and full/no-extra coverage of the documentary plan's selected event IDs.

## Deferred work

This layer is not narration generation, prose writing, scene planning, image prompting, director interpretation, or LLM storytelling. The production workflow remains unchanged until a later integration spirit adopts this structural artifact.
