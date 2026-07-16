# Runtime Baseline

## Supported production runtime

Run the supported entry point from the repository root:

```text
python -m src.cli.generate <topic> <source1> [source2 ...]
```

The active path is:

```text
src.cli.generate
→ ProductionPipeline
→ DocumentaryWorkflow
→ KnowledgeRepository
→ knowledge_v2.KnowledgeExtractionPipeline
→ RuleEngine-based extractors
→ ExtractionResult
→ GraphBuilder
→ outline, narrative, script, scene plan, scenes, image prompts
→ JSON and terminal report
```

`src/application/knowledge/graph_builder.py` is the active graph builder. New production code must use this path unless a later ADR replaces it.

## Test command and layout

Run tests from the repository root:

```text
python -m pytest
```

```text
tests/
├── unit/          # isolated current-component tests
├── integration/   # active multi-component tests
├── regression/    # fixed-bug regressions
├── smoke/         # supported runtime checks
└── legacy/        # retained obsolete tests and debug scripts; intentionally excluded
```

`pytest.ini` explicitly discovers only these active test directories. This is not a blanket exclusion: the former `src/test_*.py` files are legacy executable scripts or obsolete API tests and must not be used as evidence of current behavior.

## Runtime inventory

| Area | Classification | Notes |
| --- | --- | --- |
| `application/knowledge_v2` | ACTIVE | Active deterministic extraction wrappers. |
| `application/knowledge` | PARTIALLY_ACTIVE | Repository, graph builder, canonicalization, and metadata engines are active; the older extraction pipeline is obsolete and broken. |
| `application/workflow` | ACTIVE | `DocumentaryWorkflow` is the supported coordinator. |
| `application/documentary` | ACTIVE | Outline generation is active and template-based. |
| `application/narrative` | ACTIVE | Deterministic narrative generation is active and template-based. |
| `application/script` | ACTIVE | Script assembly is active. |
| `application/planning` | ACTIVE | Basic scene planning is active. |
| `application/scene_generation` | ACTIVE | Deterministic scene generation is active; it does not call the LLM gateway. |
| `application/image` | ACTIVE | Text prompt generation is active; no image-provider integration exists. |
| `application/llm` | PARTIALLY_ACTIVE | Provider adapters exist but are not used by the active documentary artifact path. |
| `infrastructure/storage` | DISCONNECTED | JSON storage exists but is not wired into the workflow or graph repository. |
| `domain/knowledge_objects` | ACTIVE | Used by the active repository and graph builder. |
| `domain/knowledge_graph` | ACTIVE | In-memory graph and index used by the production workflow. |

## Legacy and experimental material

- `src/test_*.py`: legacy script-style tests and obsolete API checks. They remain for reference but are intentionally outside pytest discovery.
- `tests/legacy/`: retained obsolete graph-builder test and debug script. These are not active tests.
- `application/knowledge/extraction_pipeline.py`: older candidate pipeline that imports removed extractor modules. Do not use it for new work.
- `application/knowledge/knowledge_graph_builder.py`: older graph-builder implementation. Do not use it for new work.
- `core/` and several `application/services/` modules: experimental or disconnected compatibility material unless explicitly traced from the supported runtime.

## Deferred limitations

Spirit 01 does not add persistence, retrieval, evidence provenance, contradiction detection, historical reasoning, director planning, voice, video, or publishing. It stabilizes only the current deterministic runtime and its test baseline.

## Baseline failure inventory before Spirit 01

| File(s) | Failure | Classification | Decision |
| --- | --- | --- | --- |
| `src/test_document_parser_v2.py` | `Document.paragraphs` API mismatch | LEGACY_TEST | Exclude from active discovery. |
| `src/test_documentary_generator.py`, `src/test_scene_planner.py` | Removed `generate_outline` API | OBSOLETE_API_TEST | Exclude from active discovery. |
| `src/test_extraction_pipeline_v2.py`, `v3.py`, `test_graph_query.py`, `test_pipeline_objects_v2.py`, `test_quality_metadata_v2.py`, `test_quality_pipeline_v2.py`, `test_rule_engine_v2.py` | Imports removed legacy extractor modules | OBSOLETE_API_TEST | Exclude from active discovery. |
| `src/test_graph_index.py`, `test_graph_queries.py`, `test_knowledge_graph_query.py` | Graph query/index API mismatch | LEGACY_TEST | Exclude from active discovery. |
| `src/test_object_mapper_v2.py` | Calls mapper with obsolete list API | OBSOLETE_API_TEST | Exclude from active discovery. |
| `src/test_source.py`, `src/test_timeline_event.py` | Obsolete model fields | OBSOLETE_API_TEST | Exclude from active discovery. |
| `tests/test_graph_builder_duplicate_entity.py` | Imports removed `knowledge.models` and uses unsupported builder API | OBSOLETE_API_TEST | Retain under `tests/legacy/`. |
| `tests/debug_graph_builder.py` | Manual import/debug script | EXECUTABLE_SCRIPT | Retain under `tests/legacy/`. |

The active regressions are `CURRENT_REGRESSION_TEST`. The workflow smoke test is an active integration/smoke test. No `ENVIRONMENT_DEPENDENT_TEST` is part of active discovery.
