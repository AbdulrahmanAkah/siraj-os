# Canonical Narration Planning Layer

## Purpose

Spirit 12 turns a ScriptStructure into a deterministic NarrationPlan. It plans narration roles, information priority, words, and duration without generating narration text.

## Construction

Persistent Repository
  -> KnowledgeRetriever
  -> HistoricalReasoner
  -> ClaimSelector
  -> EventEngine
  -> DocumentaryPlanner
  -> NarrativeArchitect
  -> ScriptArchitect
  -> NarrationPlanner

NarrationPlanner accepts only ScriptArchitect. It does not import or access the repository, graph, retrieval, reasoning, selection, timeline, event, documentary-planning, or narrative-architecture layers directly.

## Models

| Model | Contents |
| --- | --- |
| NarrationBlock | Stable block ID, script segment ID, narration role, information priority, word count, and position. |
| NarrationPlan | Stable plan ID, script structure ID, ordered blocks, total words, and duration in seconds. |

## Role mapping

| Script segment | Narration role |
| --- | --- |
| OPENING_HOOK | HOOK |
| BACKGROUND | CONTEXT |
| DEVELOPMENT | EXPLANATION |
| REVEAL | REVELATION |
| CLIMAX | CLIMAX_NARRATION |
| RESOLUTION | RESOLUTION |
| EPILOGUE | LEGACY_REFLECTION |

Each script segment yields exactly one block. Block ordering follows segment position, then segment ID.

## Estimates

Word count combines a segment-type base, the segment runtime estimate, and the narrative-complexity value exposed by ScriptArchitect. Duration uses a fixed 150 words per minute and is stored in seconds.

## Validation

A plan is valid only when it contains exactly one HOOK and CLIMAX_NARRATION, at least one ending role, unique block IDs, positive word counts, contiguous stable positions, and exactly one block for every script segment.

## Deferred work

This layer does not generate prose, invoke an LLM, create voice audio, plan scenes, or modify the production narration generator. Those remain future integration work.
