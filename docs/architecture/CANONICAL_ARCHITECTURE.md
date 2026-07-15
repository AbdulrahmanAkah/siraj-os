# Canonical Architecture

## Purpose

This document is the authoritative selection map for the current executable SIRAJ OS architecture. A component is canonical only when it is used by the supported runtime documented in `RUNTIME_BASELINE.md`.

## Canonical runtime

```text
CLI: src.cli.generate
→ src.application.pipeline.production_pipeline.ProductionPipeline
→ src.application.workflow.documentary_workflow.DocumentaryWorkflow
→ src.application.knowledge.knowledge_repository.KnowledgeRepository
→ src.application.knowledge_v2.pipeline.KnowledgeExtractionPipeline
→ src.application.knowledge.extraction_result.ExtractionResult
→ src.application.knowledge.graph_builder.GraphBuilder
→ src.domain.knowledge_graph.knowledge_graph.KnowledgeGraph
→ documentary artifacts
```

There is one supported production orchestration path: `ProductionPipeline` creates `DocumentaryWorkflow`; the workflow uses `KnowledgeRepository`; the repository owns the canonical extraction pipeline and graph builder.

## Canonical models

| Concept | Canonical implementation | Active runtime use |
| --- | --- | --- |
| Person | `src.domain.knowledge_objects.person.Person` | Extraction mapping and graph construction |
| Location | `src.domain.knowledge_objects.location.Location` | Extraction mapping and graph construction |
| Event | `src.domain.knowledge_objects.event.Event` | Extraction mapping and graph construction |
| Claim | `src.domain.knowledge_objects.claim.Claim` | Repository, extraction result, graph construction |
| Source | `src.domain.knowledge_objects.source.Source` | Repository, extraction result, graph construction |
| Relationship | `src.domain.knowledge_objects.relationship.Relationship` | Repository, extraction result, graph construction |
| TimelineEvent | `src.domain.knowledge_objects.timeline_event.TimelineEvent` | Repository, extraction result, graph construction |
| ExtractionResult | `src.application.knowledge.extraction_result.ExtractionResult` | Repository-to-graph contract |
| KnowledgeGraph | `src.domain.knowledge_graph.knowledge_graph.KnowledgeGraph` | Graph container used by workflow and renderers |
| GraphBuilder | `src.application.knowledge.graph_builder.GraphBuilder` | Canonical graph construction |
| KnowledgeRepository | `src.application.knowledge.knowledge_repository.KnowledgeRepository` | Canonical ingestion boundary |
| KnowledgeRetriever | `src.application.retrieval.knowledge_retriever.KnowledgeRetriever` | Canonical read-only query boundary over loaded graphs |
| HistoricalReasoner | `src.application.reasoning.historical_reasoner.HistoricalReasoner` | Canonical deterministic historical analysis over retrieval |
| ClaimSelector | `src.application.selection.claim_selector.ClaimSelector` | Canonical deterministic and explainable selection over reasoning |
| EventEngine | `src.application.events.event_engine.EventEngine` | Canonical deterministic event construction and timeline ordering over selection |
| DocumentaryPlanner | `src.application.documentary_planning.documentary_planner.DocumentaryPlanner` | Canonical deterministic documentary planning over historical timelines |
| NarrativeArchitect | `src.application.narrative_architecture.narrative_architect.NarrativeArchitect` | Canonical deterministic narrative structure over documentary plans |
| ScriptArchitect | `src.application.script_architecture.script_architect.ScriptArchitect` | Canonical deterministic script structure over narrative architecture |
| NarrationPlanner | `src.application.narration_planning.narration_planner.NarrationPlanner` | Canonical deterministic narration planning over script structure |
| ScenePlanner | `src.application.scene_planning.scene_planner.ScenePlanner` | Canonical deterministic visual scene planning over narration plans |
| StoryboardArchitect | `src.application.storyboard_architecture.storyboard_architect.StoryboardArchitect` | Canonical deterministic storyboard composition over scene plans |
| VisualAssetArchitect | `src.application.visual_asset_architecture.visual_asset_architect.VisualAssetArchitect` | Canonical deterministic visual asset requirements over storyboard architecture |
| VisualSourceSelector | `src.application.visual_source_selection.visual_source_selector.VisualSourceSelector` | Canonical deterministic visual source-category selection over visual assets |
| SourceDiscoveryArchitect | `src.application.source_discovery_architecture.source_discovery_architect.SourceDiscoveryArchitect` | Canonical deterministic discovery planning over visual source plans |
| SourceAcquisitionPlanner | `src.application.source_acquisition_planning.source_acquisition_planner.SourceAcquisitionPlanner` | Canonical deterministic acquisition planning over discovery plans |
| SourceIngestionArchitect | `src.application.source_ingestion_architecture.source_ingestion_architect.SourceIngestionArchitect` | Canonical deterministic ingestion preparation over acquisition plans |
| SourceIngestionExecutor | `src.application.source_ingestion_runtime.source_ingestion_executor.SourceIngestionExecutor` | Canonical deterministic local ingestion runtime over ingestion plans |
| RepositoryIngestionEngine | `src.application.repository_ingestion.repository_ingestion_engine.RepositoryIngestionEngine` | Canonical repository-ready document population over runtime results |
| KnowledgeExtractionPipeline | `src.application.knowledge_v2.pipeline.KnowledgeExtractionPipeline` | Canonical extraction pipeline |
| Documentary workflow | `src.application.workflow.documentary_workflow.DocumentaryWorkflow` | Canonical production coordinator |

## Dependency map

```text
KnowledgeExtractionPipeline
  → knowledge_v2 extractors
  → knowledge.RuleEngine

KnowledgeRepository
  → KnowledgeExtractionPipeline
  → ObjectMapper
  → canonical domain knowledge objects
  → ExtractionResult
  → GraphBuilder

GraphBuilder
  → canonical domain knowledge objects
  → KnowledgeGraph / KnowledgeNode / KnowledgeEdge

DocumentaryWorkflow
  → KnowledgeRepository
  → canonical graph consumers: outline, narrative, script, planning, scenes, image prompts
```

## Legacy, experimental, and disconnected components

| Component | Classification | Reason / rule |
| --- | --- | --- |
| `src.application.knowledge.extraction_pipeline.ExtractionPipeline` | LEGACY | Older pipeline imports removed extractors and is not on the supported runtime path. Do not import it. |
| `src.application.knowledge.knowledge_graph_builder.KnowledgeGraphBuilder` | LEGACY | Superseded by `GraphBuilder`; contains stale debug code and an invalid target-use order. Do not import it. |
| `src.application.knowledge.candidate_models` and old extractor modules | LEGACY | Belong to the older extraction pipeline; canonical candidates are under `knowledge_v2`. |
| `src.application.knowledge_v2.candidate_models` | ACTIVE | Used by the canonical extraction pipeline. |
| `src.domain.knowledge_objects.entity.Person`, `Place`, `Event` | LEGACY | Used only by `core/` and stale scripts. Canonical active models are `person.py`, `location.py`, and `event.py`. |
| `src.core.*` | DISCONNECTED | Not imported by the supported production workflow. Retained for future consolidation decisions only. |
| `src.application.services.*` | EXPERIMENTAL / DISCONNECTED | Not used by the supported workflow unless explicitly traced. |
| `src.application.models.knowledge.*` | EXPERIMENTAL | Candidate/DTO set for the older pipeline; not the active domain model set. |
| `src.archive.legacy.*` | LEGACY | Compatibility wrappers and archived domain references. |
| `src.infrastructure.storage.JsonStorage` | DISCONNECTED | Exists but is not wired into the workflow or graph repository. |
| `src.application.documentary.DocumentaryGenerator` | LEGACY | Not used by the supported orchestration path; stale tests target removed methods. |
| `src.application.knowledge.graph_query.GraphQuery` and `src.domain.knowledge_graph.knowledge_graph_query.KnowledgeGraphQuery` | LEGACY | Direct-graph query helpers; use `KnowledgeRetriever` for new retrieval consumers. |
| `src.application.knowledge.fact_verification_engine.FactVerificationEngine` | LEGACY COMPATIBILITY | Active workflow metadata helper; not the canonical historical reasoning API. |

## Rules for contributors

1. New production extraction code imports `KnowledgeExtractionPipeline` only from `application.knowledge_v2.pipeline`.
2. New production graph code imports `GraphBuilder` only from `application.knowledge.graph_builder`.
3. New production knowledge objects import the canonical domain models listed above.
4. New workflow behavior extends `DocumentaryWorkflow`; do not introduce a second production coordinator.
5. Do not import a component classified as LEGACY, EXPERIMENTAL, or DISCONNECTED without a superseding ADR and migration test.
6. New retrieval consumers use `KnowledgeRetriever` rather than traversing `KnowledgeGraph` internals directly.
7. New historical analysis uses `HistoricalReasoner` and supplies it with a `KnowledgeRetriever`.
8. New planning consumers use `ClaimSelector` instead of enumerating all claims directly.
9. New historical event and timeline consumers use `EventEngine` rather than assembling events from claims directly.
10. New documentary-structure consumers use `DocumentaryPlanner` rather than assigning events directly to outline sections.
11. New narrative-structure consumers use `NarrativeArchitect` rather than deriving beat roles from events or claims.
12. New script-structure consumers use `ScriptArchitect` rather than deriving segment roles from documentary plans or lower layers.
13. New narration-planning consumers use `NarrationPlanner` rather than deriving narration roles from narrative or documentary structures.
14. New visual-planning consumers use `ScenePlanner` rather than deriving scene structure from script, narrative, or knowledge layers.
15. New storyboard-planning consumers use `StoryboardArchitect` rather than deriving frame structure from scenes or lower layers.
16. New visual-asset consumers use `VisualAssetArchitect` rather than deriving asset requirements from frames or lower layers.
17. New visual-source consumers use `VisualSourceSelector` rather than discovering source categories from lower layers or external systems.
18. New source-discovery consumers use `SourceDiscoveryArchitect` rather than performing discovery or external access during architecture planning.
19. New source-acquisition consumers use `SourceAcquisitionPlanner` rather than performing retrieval or external access during planning.
20. New source-ingestion consumers use `SourceIngestionArchitect` rather than parsing, ingesting, or mutating repository data during architecture planning.
21. New ingestion-runtime consumers use `SourceIngestionExecutor` only with explicit local in-memory payloads; runtime code must not perform external access or repository mutation.
22. New repository-population consumers use `RepositoryIngestionEngine` only with `IngestionExecutionResult`; repository ingestion must not perform reasoning, extraction, event creation, or external access.

## Consolidation boundary

Spirit 02 establishes canonical ownership and dependency direction only. It does not delete legacy code, redesign models, or add Knowledge OS capabilities. Physical deletion or migration of disconnected components is deferred until canonical-model consolidation can be performed with replacement coverage.
