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

There is one supported production orchestration path: `ProductionPipeline` creates `DocumentaryWorkflow`; the workflow uses the existing `src.application.knowledge.knowledge_repository.KnowledgeRepository` compatibility boundary. Spirit 22 adds the separate `src.application.knowledge_repository.KnowledgeRepository` repository-core path for `RepositoryDocument` values without changing CLI behavior.

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
| Workflow KnowledgeRepository | `src.application.knowledge.knowledge_repository.KnowledgeRepository` | Existing CLI workflow ingestion compatibility boundary |
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
| KnowledgeRepository | `src.application.knowledge_repository.knowledge_repository.KnowledgeRepository` | Canonical deterministic in-memory knowledge repository over repository documents |
| RepositoryQueryEngine | `src.application.repository_query.repository_query_engine.RepositoryQueryEngine` | Canonical deterministic exact query layer over knowledge records |
| RetrievalIndexBuilder | `src.application.retrieval.retrieval_index_builder.RetrievalIndexBuilder` | Canonical deterministic retrieval-index construction over query results |
| RetrievalRuntimeEngine | `src.application.retrieval.retrieval_runtime_engine.RetrievalRuntimeEngine` | Canonical deterministic indexed retrieval runtime |
| ClaimExtractionArchitect | `src.application.claim_extraction.claim_extraction_architect.ClaimExtractionArchitect` | Canonical deterministic claim-extraction policy architecture |
| ClaimExtractionRuntime | `src.application.claim_extraction.claim_extraction_runtime.ClaimExtractionRuntime` | Canonical deterministic claim extraction over retrieval results |
| EntityExtractionArchitect | `src.application.entity_extraction.entity_extraction_architect.EntityExtractionArchitect` | Canonical deterministic entity-extraction policy architecture |
| EntityExtractionRuntime | `src.application.entity_extraction.entity_extraction_runtime.EntityExtractionRuntime` | Canonical deterministic entity extraction over claims |
| EventExtractionArchitect | `src.application.event_extraction.event_extraction_architect.EventExtractionArchitect` | Canonical deterministic event-extraction policy architecture |
| EventExtractionRuntime | `src.application.event_extraction.event_extraction_runtime.EventExtractionRuntime` | Canonical deterministic event extraction over claims and entities |
| RelationshipGraphArchitect | `src.application.relationship_graph.relationship_graph_architect.RelationshipGraphArchitect` | Canonical deterministic relationship-graph policy architecture |
| RelationshipGraphRuntime | `src.application.relationship_graph.relationship_graph_runtime.RelationshipGraphRuntime` | Canonical deterministic graph construction over claims, entities, and events |
| HistoricalTimelineArchitect | `src.application.historical_timeline.historical_timeline_architect.HistoricalTimelineArchitect` | Canonical deterministic historical-timeline policy architecture |
| HistoricalTimelineRuntime | `src.application.historical_timeline.historical_timeline_runtime.HistoricalTimelineRuntime` | Canonical deterministic chronological timeline construction over events and relationship graphs |
| EvidenceResolutionArchitect | `src.application.evidence_resolution.evidence_resolution_architect.EvidenceResolutionArchitect` | Canonical deterministic evidence-resolution policy architecture |
| EvidenceResolutionRuntime | `src.application.evidence_resolution.evidence_resolution_runtime.EvidenceResolutionRuntime` | Canonical deterministic exact evidence collection and resolution over claims, entities, events, graphs, and timelines |
| MultiSourceCorrelationArchitect / Runtime | `src.application.multi_source_correlation` | Deterministic exact-source correlation |
| HistoricalConsistencyArchitect / Runtime | `src.application.historical_consistency` | Deterministic structural consistency checks |
| ContradictionArchitect / Runtime | `src.application.contradiction_detection` | Deterministic explicit-value contradiction checks |
| SourceReliabilityArchitect / Runtime | `src.application.source_reliability` | Deterministic source reliability scoring |
| EvidenceWeightArchitect / Runtime | `src.application.evidence_weighting` | Deterministic evidence weighting |
| KnowledgeConfidenceArchitect / Runtime | `src.application.knowledge_confidence` | Deterministic knowledge confidence scoring |
| HistoricalReasoningArchitect / Runtime | `src.application.historical_reasoning_foundation` | Deterministic traceable historical reasoning foundation |
| CausalReasoningArchitect / Runtime | `src.application.causal_reasoning` | Explicit-evidence causal reasoning |
| TemporalReasoningArchitect / Runtime | `src.application.temporal_reasoning` | Timeline-only temporal reasoning |
| NarrativeReasoningArchitect / Runtime | `src.application.narrative_reasoning` | Ordered-event narrative reasoning |
| HistoricalInterpretationArchitect / Runtime | `src.application.historical_interpretation` | Evidence-traceable historical interpretation |
| ReasoningValidationArchitect / Runtime | `src.application.reasoning_validation` | Deterministic reasoning validation |
| DocumentaryPlanningArchitectV2 / RuntimeV2 | `src.application.documentary_planning_v2` | Validated, traceable Documentary Planning v2 |
| NarrativeArchitectureArchitectV2 / RuntimeV2 | `src.application.narrative_architecture_v2` | Deterministic narrative beats from plan chapters |
| DocumentaryScriptArchitect / Runtime | `src.application.documentary_script_runtime` | Evidence-referenced script structure |
| SceneGenerationArchitect / Runtime | `src.application.scene_generation_runtime` | Deterministic scenes from script sections |
| StoryboardArchitectRuntime / Runtime | `src.application.storyboard_runtime` | Evidence-linked frames from scenes |
| DocumentaryAssemblyArchitect / Runtime | `src.application.documentary_assembly` | Traceable documentary package assembly |
| VisualEvidenceArchitect / Runtime | `src.application.visual_evidence` | Visual evidence mapping |
| SourceAttributionArchitect / Runtime | `src.application.source_attribution` | Deterministic artifact attribution |
| DocumentaryVerificationArchitect / Runtime | `src.application.documentary_verification` | Documentary coverage and integrity validation |
| PublicationPackagingArchitect / Runtime | `src.application.publication_packaging` | Verified publication package construction |
| ExportArchitect / Runtime | `src.application.export_architecture` | Architecture-only export manifest and job bundle |
| ProductionArchitect / Runtime | `src.application.production_runtime` | Final production-ready documentary aggregate |
| PersistenceArchitect / Runtime | `src.application.persistence_architecture` | Database-agnostic persistence manifest architecture |
| RepositoryPersistenceArchitect / Runtime | `src.application.repository_persistence` | Deterministic in-memory save and restore runtime |
| SnapshotArchitect / Runtime | `src.application.snapshot_engine` | Manifest-integrity snapshot creation |
| VersioningArchitect / Runtime | `src.application.versioning_engine` | Deterministic repository and artifact version records |
| AuditTrailArchitect / Runtime | `src.application.audit_trail` | Deterministic who/what/when/why audit records |
| ReproducibilityArchitect / Runtime | `src.application.reproducibility` | Exact input/configuration/version reproduction manifests |
| WorkflowArchitect / Runtime | `src.application.workflow_runtime` | Local deterministic workflow definitions and executions |
| JobOrchestrationArchitect / Runtime | `src.application.job_orchestration` | In-memory FIFO job orchestration |
| ExecutionMonitoringArchitect / Runtime | `src.application.execution_monitoring` | Deterministic execution metrics and reports |
| DiagnosticsArchitect / Runtime | `src.application.diagnostics` | Integrity and execution diagnostic reports |
| RecoveryArchitect / Runtime | `src.application.recovery_architecture` | Snapshot-based recovery planning |
| OperationalArchitect / Runtime | `src.application.operational_runtime` | Final deterministic operational state aggregate |
| Bundle E Scale & Performance layers | `src.application.index_optimization` through `src.application.performance_verification` | Deterministic local index, query, graph, timeline, cache, incremental, parallel, memory, benchmark, and verification contracts |
| Bundle G Historical Intelligence | `src.application.historical_intelligence` | Traceable comparative, structural, strategic, trend, theory, synthesis, and validation intelligence contracts |
| Bundle F Documentary Production | `src.application.production_contracts` through `src.application.production_verification_engine` | Deterministic, integer-time, externally renderable documentary production specification |
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

KnowledgeRepository (Spirit 22 repository core)
  → RepositoryIngestionEngine
  → RepositoryDocument
  → KnowledgeRecord / RepositorySnapshot

RepositoryQueryEngine
  → KnowledgeRepository
  → KnowledgeRecord / RepositorySnapshot

RetrievalIndexBuilder
  → RepositoryQueryEngine
  → RetrievalIndex / IndexEntry

RetrievalRuntimeEngine
  → RetrievalIndexBuilder
  → RetrievalRequest / RetrievalResult

ClaimExtractionArchitect
  → RetrievalRuntimeEngine
  → ClaimExtractionPlan

ClaimExtractionRuntime
  → RetrievalRuntimeEngine
  → ClaimExtractionPlan / ClaimRecord / ClaimEvidence

EntityExtractionArchitect
  → ClaimExtractionRuntime
  → EntityExtractionPlan

EntityExtractionRuntime
  → ClaimExtractionRuntime
  → EntityExtractionPlan / EntityRecord / EntityEvidence

EventExtractionArchitect
  → ClaimExtractionRuntime / EntityExtractionRuntime
  → EventExtractionPlan

EventExtractionRuntime
  → ClaimExtractionRuntime / EntityExtractionRuntime
  → EventExtractionPlan / EventRecord / EventEvidence

RelationshipGraphArchitect
  → EntityExtractionRuntime / EventExtractionRuntime
  → RelationshipGraph

RelationshipGraphRuntime
  → EntityExtractionRuntime / EventExtractionRuntime
  → GraphNode / GraphEdge / RelationshipGraphResult

HistoricalTimelineArchitect
  → EventExtractionRuntime / RelationshipGraphRuntime
  → TimelinePlan

HistoricalTimelineRuntime
  → EventExtractionRuntime / RelationshipGraphRuntime
  → TimelineEntry / HistoricalTimeline / TimelineBuildResult

EvidenceResolutionArchitect
  → EvidenceResolutionPlan

EvidenceResolutionRuntime
  → ClaimExtractionResult / EntityExtractionResult / EventExtractionResult
  → RelationshipGraph / HistoricalTimeline
  → ResolvedEvidence / EvidenceBundle / EvidenceResolutionResult

MultiSourceCorrelationRuntime
  → ClaimExtractionResult / EntityExtractionResult / EventExtractionResult
  → CorrelationGroup / CorrelationResult

HistoricalConsistencyRuntime
  → EventExtractionResult / RelationshipGraph / HistoricalTimeline
  → ConsistencyReport / ConsistencyResult

ContradictionRuntime
  → ClaimExtractionResult
  → ContradictionRecord / ContradictionResult

SourceReliabilityRuntime
  → EvidenceResolutionResult / ContradictionResult
  → SourceReliabilityScore / ReliabilityResult

EvidenceWeightRuntime
  → EvidenceResolutionResult / ReliabilityResult / CorrelationResult
  → EvidenceWeight / EvidenceWeightResult

KnowledgeConfidenceRuntime
  → EvidenceWeightResult / ReliabilityResult / ContradictionResult
  → ConfidenceRecord / KnowledgeConfidenceResult

HistoricalReasoningArchitect / HistoricalReasoningRuntime
  → HistoricalTimeline / RelationshipGraph
  → EvidenceResolutionResult / KnowledgeConfidenceResult
  → HistoricalReasoningPlan / ReasoningChain / ReasoningResult

CausalReasoningArchitect / CausalReasoningRuntime
  → ClaimExtractionResult / ReasoningResult
  → CausalReasoningPlan / CausalRelation / CausalReasoningResult

TemporalReasoningArchitect / TemporalReasoningRuntime
  → HistoricalTimeline
  → TemporalReasoningPlan / TemporalRelation / TemporalReasoningResult

NarrativeReasoningArchitect / NarrativeReasoningRuntime
  → HistoricalTimeline / ReasoningResult
  → NarrativeReasoningPlan / NarrativeReasoningResult

HistoricalInterpretationArchitect / HistoricalInterpretationRuntime
  → ReasoningResult / CausalReasoningResult / TemporalReasoningResult
  → NarrativeReasoningResult / EvidenceResolutionResult
  → HistoricalInterpretationPlan / HistoricalInterpretationResult

ReasoningValidationArchitect / ReasoningValidationRuntime
  → ReasoningResult / HistoricalInterpretationResult
  → HistoricalTimeline / RelationshipGraph / EvidenceResolutionResult
  → ContradictionResult / ValidatedReasoningResult

DocumentaryPlanningArchitectV2 / DocumentaryPlanningRuntimeV2
  → ValidatedReasoningResult / HistoricalTimeline / RelationshipGraph
  → HistoricalInterpretationResult
  → DocumentaryPlanningPolicy / DocumentaryPlan

Bundle C Documentary Intelligence
  → DocumentaryPlan → NarrativeArchitecture → DocumentaryScript → ScenePlanRuntime → Storyboard
  → DocumentaryPackage → VisualEvidenceMap / AttributionResult → VerificationReport
  → PublicationPackage → ExportBundle → ProductionReadyDocumentary

Bundle D Persistence & Operations
  → PersistenceManifest → RepositoryPersistenceResult → SnapshotResult → VersionResult
  → AuditTrail / ReproducibilityResult → WorkflowExecution → JobQueue / JobResult
  → ExecutionReport → DiagnosticsReport → RecoveryManifest → OperationalState

Bundle E Scale & Performance
  → OptimizedIndex → QueryPlan / QueryResultProfile → GraphOptimizationResult / TimelineOptimizationResult
  → CacheManifest / IncrementalResult / ParallelPlan / MemoryOptimizationResult
  → BenchmarkReport → PerformanceVerificationReport

Bundle G Historical Intelligence
  → Comparative / Cross-Era / Pattern / Civilization / Institution / Strategic / Trend
  → Counterfactual Constraints / Theory Evaluation → HistoricalIntelligencePackage → ValidatedHistoricalIntelligence

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
23. New knowledge consumers use the canonical `KnowledgeRepository` over `RepositoryDocument` values; repository-core code must not perform claims, reasoning, timeline, documentary, narrative, or LLM operations.
24. New query consumers use `RepositoryQueryEngine` for exact deterministic access over `KnowledgeRepository`; query code must not perform semantic, vector, ranking, embedding, AI, or external search operations.
25. New retrieval consumers use `RetrievalRuntimeEngine` over a validated `RetrievalIndex`; runtime retrieval must not scan repositories directly or perform semantic, vector, ranking, embedding, AI, or external search operations.
26. New claim consumers use `ClaimExtractionRuntime` with `ClaimExtractionArchitect` plans and retrieval results; claim extraction must not perform entity, event, relationship, reasoning, narrative, LLM, or external API operations.
27. New entity consumers use `EntityExtractionRuntime` with claim extraction results; entity extraction must use only canonical deterministic strategies and must not perform event, relationship, timeline, reasoning, narrative, NLP, LLM, or external API operations.
28. New event consumers use `EventExtractionRuntime` with claim and entity extraction results; event extraction must not perform relationship, timeline, reasoning, narrative, NLP, LLM, or external API operations.
29. New graph consumers use `RelationshipGraphRuntime` with claim, entity, and event extraction results; graph construction must not perform timeline, reasoning, narrative, NLP, LLM, or external API operations.
30. New timeline consumers use `HistoricalTimelineRuntime` with event extraction results and relationship graphs; timeline construction must preserve explicit dates only and must not perform inference, estimation, reasoning, narrative, NLP, LLM, documentary, or external API operations.
31. New evidence consumers use `EvidenceResolutionRuntime` with extraction results, relationship graphs, and historical timelines; resolution must use exact evidence text and source-content equality only and must not perform correlation, consistency or contradiction analysis, reasoning, narrative, NLP, LLM, or external API operations.
32. Knowledge-quality consumers use Bundle A runtime layers in dependency order. They must use exact equality and deterministic rule checks only; they must not perform semantic matching, inference, NLP, LLM, external access, or probabilistic scoring.
33. Historical reasoning consumers use Bundle B layers in canonical order. Foundation reasoning requires explicit timeline, graph, and resolved-evidence links; causal and temporal relations may use only exact claim patterns and explicit dates.
34. Historical interpretations must preserve complete chain-to-source traces, and reasoning output must pass all five canonical `ReasoningValidationRuntime` checks before downstream documentary intelligence can consume it.
35. Bundle C models use deterministic IDs, canonical timestamps, stable positions, and trace metadata. Documentary Planning v2 accepts only valid reasoning and must copy documentary structure from explicit supported records without creative generation.
36. Bundle C downstream layers may consume only the immediately preceding canonical documentary artifact and its explicit traces. They must not generate media, prompts, narration prose, semantic interpretations, or external side effects.
37. Bundle D persistence and operations use canonical in-memory contracts only. They must remain database-, queue-, API-, and network-independent; all operational identities, timestamps, versions, hashes, ordering, and recovery actions must be deterministic.
38. Bundle E performance layers are local deterministic contracts. They must not introduce external infrastructure or wall-clock-dependent pass/fail behavior; partitioning, plans, profiles, benchmarks, and verification must use stable content-derived metadata.

## Consolidation boundary

Spirit 02 establishes canonical ownership and dependency direction only. It does not delete legacy code, redesign models, or add Knowledge OS capabilities. Physical deletion or migration of disconnected components is deferred until canonical-model consolidation can be performed with replacement coverage.
