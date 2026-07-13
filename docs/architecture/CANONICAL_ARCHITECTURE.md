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

## Rules for contributors

1. New production extraction code imports `KnowledgeExtractionPipeline` only from `application.knowledge_v2.pipeline`.
2. New production graph code imports `GraphBuilder` only from `application.knowledge.graph_builder`.
3. New production knowledge objects import the canonical domain models listed above.
4. New workflow behavior extends `DocumentaryWorkflow`; do not introduce a second production coordinator.
5. Do not import a component classified as LEGACY, EXPERIMENTAL, or DISCONNECTED without a superseding ADR and migration test.
6. New retrieval consumers use `KnowledgeRetriever` rather than traversing `KnowledgeGraph` internals directly.

## Consolidation boundary

Spirit 02 establishes canonical ownership and dependency direction only. It does not delete legacy code, redesign models, or add Knowledge OS capabilities. Physical deletion or migration of disconnected components is deferred until canonical-model consolidation can be performed with replacement coverage.
