# Canonical Script Architecture Layer

## Purpose

Spirit 11 converts a NarrativeArchitecture into a deterministic ScriptStructure. It defines script-segment roles and timing without generating script prose.

## Construction

Persistent Repository
  -> KnowledgeRetriever
  -> HistoricalReasoner
  -> ClaimSelector
  -> EventEngine
  -> DocumentaryPlanner
  -> NarrativeArchitect
  -> ScriptArchitect

ScriptArchitect accepts only NarrativeArchitect. It does not directly import or access the repository, graph, retrieval, reasoning, selection, timeline, event, or documentary-planning layers.

## Models

| Model | Contents |
| --- | --- |
| ScriptSegment | Stable segment ID, source beat ID, segment type, purpose, estimated duration, and position. |
| ScriptStructure | Stable structure ID, narrative architecture ID, ordered segments, estimated runtime, and segment count. |

## Mapping rules

| Narrative beat | Script segment |
| --- | --- |
| SETUP | OPENING_HOOK |
| CONTEXT | BACKGROUND |
| ESCALATION | DEVELOPMENT |
| TURNING_POINT | REVEAL |
| CLIMAX | CLIMAX |
| AFTERMATH | RESOLUTION |
| LEGACY | EPILOGUE |

Each beat creates exactly one segment. Segments are ordered by beat position, then stable beat ID. Segment durations use deterministic base duration, bounded event count, and the architecture complexity level.

## Validation

A script structure is valid only when it contains exactly one OPENING_HOOK and CLIMAX, at least one RESOLUTION or EPILOGUE, unique segment IDs, contiguous stable positions, and exactly one segment for every narrative beat.

## Deferred work

This layer is not prose generation, narration generation, scene planning, image prompting, voice synthesis, or LLM script writing. The existing production script generator remains unchanged until a later integration spirit adopts the structural artifact.
