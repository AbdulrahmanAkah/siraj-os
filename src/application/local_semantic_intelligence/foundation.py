"""Foundation reports, pilot selection, configuration, and CLI-facing runtime."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Callable

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
    integrity_hash,
)

from .models import (
    SEMANTIC_SCHEMA_VERSION,
    STAGES,
    SemanticHardwareProfile,
    SemanticProviderError,
    SemanticSegmentInput,
)
from .ollama_provider import (
    OllamaLocalSemanticConfig,
    OllamaLocalSemanticProvider,
)
from .orchestrator import (
    LocalSemanticOrchestrator,
    atomic_write_json,
    atomic_write_text,
)
from .provider import SemanticExtractionProvider
from .semantic_prompts import prompt_manifest


FOUNDATION_VERSION = "local-semantic-intelligence-foundation-v1"
PILOT_SIZE = 12


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"INVALID_JSON:{path.name}:{error.lineno}:{error.colno}"
        ) from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path.name}")
    return value


def _annotation_categories(
    annotation: dict[str, Any],
    manifest_entry: dict[str, Any],
) -> list[str]:
    current = annotation.get("current_extraction", {})
    reasons = set(map(str, manifest_entry.get("selection_reasons", [])))
    categories: list[str] = []
    entities = current.get("entities", [])
    if entities and annotation.get("reviewer_notes", "").strip():
        categories.append("ENTITY_BOUNDARY_FAILURE")
    event_types = {
        str(item.get("event_type", "")).upper()
        for item in current.get("events", [])
    }
    predicates = {
        str(item.get("predicate", "")).upper()
        for item in current.get("claims", [])
    }
    if any(
        token in value
        for value in event_types | predicates
        for token in ("APPOINT", "DISMISS", "REPLACE", "RULED", "LED")
    ):
        categories.append("APPOINTMENT_OR_DISMISSAL")
    if current.get("isnad_chains") or "CURRENT_ISNAD_CHAIN" in reasons:
        categories.append("ISNAD")
    if (
        int(annotation.get("book_id", -1)) == 619
        or "POETRY_OR_SHORT_LINE_STRUCTURE" in reasons
    ):
        categories.append("POETRY_OR_SIRA")
    if any(
        token in value
        for value in event_types | predicates
        for token in ("INSTITUTION", "OFFICE", "RULED", "FOUNDED")
    ):
        categories.append("INSTITUTION")
    temporal_types = {
        str(item.get("temporal_type", "")).upper()
        for item in current.get("temporal_mentions", [])
    }
    if temporal_types & {
        "RELATIVE",
        "BEFORE_EVENT",
        "AFTER_EVENT",
        "APPROXIMATE",
        "UNRESOLVED",
    }:
        categories.append("RELATIVE_TEMPORAL_EXPRESSION")
    elif "TEMPORAL_EXPRESSION" in reasons:
        categories.append("TEMPORAL_EXPRESSION_CANDIDATE")
    if "NEGATIVE_CONTROL_NO_CURRENT_SIGNAL" in reasons:
        categories.append("NEGATIVE_CONTROL")
    if "HEADING_BEARING_SEGMENT" in reasons:
        categories.append("HEADING_BOUNDARY")
    if annotation.get("reviewer_notes", "").strip():
        categories.append("HUMAN_DIAGNOSTIC_NOTE")
    return sorted(set(categories))


def select_pilot_12(
    gold: dict[str, Any],
    audit_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Choose a stable, category-covering subset without reading expected labels."""

    manifest_by_id = {
        str(item["audit_segment_id"]): item
        for item in audit_manifest.get("segments", [])
    }
    candidates: list[dict[str, Any]] = []
    for annotation in gold.get("annotations", []):
        audit_id = str(annotation["audit_segment_id"])
        manifest_entry = manifest_by_id.get(audit_id, {})
        categories = _annotation_categories(annotation, manifest_entry)
        candidates.append(
            {
                "audit_segment_id": audit_id,
                "annotation": annotation,
                "manifest": manifest_entry,
                "categories": categories,
            }
        )
    candidates.sort(
        key=lambda item: (
            int(item["annotation"]["book_id"]),
            int(item["annotation"]["segment_id"]),
            item["audit_segment_id"],
        )
    )

    targets = (
        "ENTITY_BOUNDARY_FAILURE",
        "APPOINTMENT_OR_DISMISSAL",
        "ISNAD",
        "POETRY_OR_SIRA",
        "INSTITUTION",
        "RELATIVE_TEMPORAL_EXPRESSION",
        "TEMPORAL_EXPRESSION_CANDIDATE",
        "NEGATIVE_CONTROL",
        "HEADING_BOUNDARY",
        "HUMAN_DIAGNOSTIC_NOTE",
    )
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for target in targets:
        match = next(
            (
                item
                for item in candidates
                if item["audit_segment_id"] not in used
                and target in item["categories"]
            ),
            None,
        )
        if match:
            selected.append(match)
            used.add(match["audit_segment_id"])
    for item in candidates:
        if len(selected) >= PILOT_SIZE:
            break
        if item["audit_segment_id"] not in used:
            selected.append(item)
            used.add(item["audit_segment_id"])
    if len(selected) != PILOT_SIZE:
        raise ValueError("PILOT_12_REQUIRES_AT_LEAST_TWELVE_GOLD_SEGMENTS")
    return sorted(
        selected,
        key=lambda item: item["audit_segment_id"],
    )


def _segment_input(item: dict[str, Any]) -> SemanticSegmentInput:
    annotation = item["annotation"]
    return SemanticSegmentInput(
        audit_segment_id=str(annotation["audit_segment_id"]),
        source_id=str(annotation["source_id"]),
        locator=str(annotation["locator"]),
        original_text=str(annotation["original_text"]),
        book_id=int(annotation["book_id"]),
        book_title=str(annotation.get("book_title", "")),
        segment_id=int(annotation["segment_id"]),
        current_extraction=dict(annotation.get("current_extraction", {})),
        reviewer_notes=str(annotation.get("reviewer_notes", "")),
        selection_reasons=list(item["categories"]),
    )


def _semantic_schema() -> dict[str, Any]:
    span = {
        "type": "object",
        "required": ["start", "end", "text"],
        "properties": {
            "start": {"type": "integer", "minimum": 0},
            "end": {"type": "integer", "minimum": 1},
            "text": {"type": "string", "minLength": 1},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SEMANTIC_SCHEMA_VERSION,
        "title": "Siraj Local Semantic Extraction V2",
        "definitions": {
            "EvidenceSpan": span,
            "StructuralClassification": {
                "type": "object",
                "required": [
                    "segment_type",
                    "confidence",
                    "rationale_codes",
                ],
            },
            "EntityMentionV2": {
                "type": "object",
                "required": [
                    "mention_id",
                    "exact_surface",
                    "start",
                    "end",
                    "entity_types",
                    "evidence",
                    "source_id",
                    "locator",
                ],
            },
            "EventV2": {
                "type": "object",
                "required": [
                    "event_id",
                    "event_type",
                    "trigger",
                    "evidence",
                    "participants",
                    "places",
                    "institutions_offices",
                    "temporal_links",
                    "modality",
                    "attribution",
                ],
                "description": (
                    "Participants and places are role-bearing references with "
                    "mention_reference or exact_surface."
                ),
            },
            "RelationV2": {
                "type": "object",
                "required": [
                    "relation_id",
                    "subject_mention",
                    "predicate",
                    "object_reference",
                    "evidence",
                    "explicit_or_inferred",
                ],
            },
            "ClaimV2": {
                "type": "object",
                "required": [
                    "claim_id",
                    "proposition",
                    "speaker_or_source",
                    "assertion_status",
                    "evidence",
                    "source_attribution_chain",
                ],
            },
            "IsnadV2": {
                "type": "object",
                "required": [
                    "isnad_id",
                    "ordered_narrators",
                    "exact_chain_range",
                ],
            },
            "TemporalV2": {
                "type": "object",
                "required": [
                    "temporal_id",
                    "exact_expression",
                    "evidence",
                    "calendar",
                    "precision",
                ],
            },
            "InstitutionOfficeV2": {
                "type": "object",
                "required": [
                    "record_id",
                    "institution",
                    "office",
                    "action",
                    "evidence",
                ],
            },
        },
    }


def initialize_semantic_foundation(
    audit_root: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    audit = Path(audit_root).resolve()
    output = Path(output_root).resolve()
    if output == audit or audit in output.parents:
        raise ValueError("SEMANTIC_OUTPUT_MUST_NOT_MUTATE_GOLD_AUDIT")
    gold = _read_json(audit / "gold-annotation-template.json")
    manifest = _read_json(audit / "audit-sample-manifest.json")
    selected = select_pilot_12(gold, manifest)
    pilot = []
    for item in selected:
        segment = _segment_input(item)
        segment_path = output / "segments" / segment.audit_segment_id / "segment-input.json"
        atomic_write_json(
            segment_path,
            {
                "schema_version": SEMANTIC_SCHEMA_VERSION,
                **asdict(segment),
                "expected_gold_labels_loaded": False,
                "knowledge_graph_write_allowed": False,
            },
        )
        for position, stage in enumerate(STAGES, 1):
            stage_path = (
                segment_path.parent
                / f"{position:02d}-{stage.lower()}.json"
            )
            if not stage_path.exists():
                atomic_write_json(
                    stage_path,
                    {
                        "schema_version": SEMANTIC_SCHEMA_VERSION,
                        "stage": stage,
                        "status": "NOT_RUN",
                        "audit_segment_id": segment.audit_segment_id,
                        "reason_codes": ["PENDING_EXPLICIT_LOCAL_MODEL_RUN"],
                        "graph_written": False,
                    },
                )
        pilot.append(
            {
                "audit_segment_id": segment.audit_segment_id,
                "source_id": segment.source_id,
                "locator": segment.locator,
                "book_id": segment.book_id,
                "book_title": segment.book_title,
                "segment_id": segment.segment_id,
                "selection_reasons": segment.selection_reasons,
                "reviewer_notes_present": bool(segment.reviewer_notes.strip()),
                "reviewer_notes_used_as_final_labels": False,
                "input_hash": integrity_hash(asdict(segment)),
                "input_artifact": (
                    f"segments/{segment.audit_segment_id}/segment-input.json"
                ),
            }
        )

    pilot_id = deterministic_id(
        "local_semantic_pilot",
        [
            SEMANTIC_SCHEMA_VERSION,
            [item["audit_segment_id"] for item in pilot],
            [item["input_hash"] for item in pilot],
        ],
    )
    config = {
        "schema_version": "local-semantic-provider-config-v1",
        "provider": {
            "provider_id": "OLLAMA_LOCAL_SEMANTIC",
            "endpoint": "http://127.0.0.1:11434",
            "model_reference": "qwen3:4b-instruct",
            "model_digest": "UNRESOLVED",
            "model_policy": "PILOT_MODEL_ONLY",
            "profile": "LOCAL_ONLY",
            "connect_timeout_seconds": 10,
            "model_load_timeout_seconds": 300,
            "generation_timeout_seconds": 900,
            "overall_stage_timeout_seconds": 900,
            "retries": 1,
            "stream": False,
            "temperature": 0,
            "thinking": False,
            "raw_response_retention": "SAFE_LOCAL_ARTIFACT",
        },
        "hardware": asdict(SemanticHardwareProfile()),
        "policy": {
            "external_network_allowed": False,
            "loopback_only": True,
            "automatic_model_download": False,
            "cloud_fallback": False,
            "maximum_loaded_models": 1,
            "bulk_processing_enabled": False,
        },
    }
    pilot_manifest = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "foundation_version": FOUNDATION_VERSION,
        "pilot_id": pilot_id,
        "created_at": CANONICAL_TIMESTAMP,
        "selection_policy": "DETERMINISTIC_CATEGORY_COVERAGE_THEN_STABLE_ORDER",
        "sample_count": len(pilot),
        "segments": pilot,
        "gold_expected_annotations_consumed": False,
        "reviewer_notes_role": "HUMAN_DIAGNOSTIC_CONTEXT_ONLY",
    }
    reports = {
        "provider-config.example.json": config,
        "semantic-schema-v2.json": _semantic_schema(),
        "prompt-manifest.json": prompt_manifest(),
        "pilot-12-manifest.json": pilot_manifest,
        "benchmark-run-manifest.json": {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "status": "NOT_RUN_MODEL_NOT_CONFIGURED",
            "pilot_id": pilot_id,
            "sample": "pilot-12",
            "execution_policy": "SEQUENTIAL_ONE_MODEL_ONE_SEGMENT",
            "stage_order": list(STAGES),
            "resume_supported": True,
        },
        "reconciliation-report.json": {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "status": "PENDING_PILOT_EXECUTION",
            "counts": {},
            "knowledge_graph_written": False,
        },
        "learning-report.json": {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "status": "PENDING_PILOT_EXECUTION",
            "automatic_rule_changes_allowed": False,
        },
        "performance-report.json": {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "status": "PENDING_PILOT_EXECUTION",
            "metrics": [
                "model_load_time",
                "stage_latency",
                "total_latency",
                "tokens_if_available",
                "peak_process_memory_if_measurable",
                "schema_failures",
                "validation_rejections",
                "cache_hits",
            ],
            "wall_clock_is_not_a_correctness_gate": True,
        },
        "validation-report.json": {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "status": "VALID_FOUNDATION_PENDING_REAL_MODEL",
            "pilot_count_valid": len(pilot) == PILOT_SIZE,
            "loopback_only": True,
            "external_network_used": False,
            "shamela_installation_accessed": False,
            "gold_annotations_modified": False,
            "knowledge_graph_written": False,
        },
        "adaptive-execution-plan.json": {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "status": "READY_FOR_SINGLE_SEGMENT",
            "plans": {
                "SIMPLE_HISTORICAL": ["LLM_CALL_EXECUTED", "REUSED_FROM_COMBINED_CALL", "DETERMINISTIC_ONLY"],
                "ISNAD": ["LLM_CALL_EXECUTED", "DETERMINISTIC_ONLY"],
                "POETRY_SIRA": ["LLM_CALL_EXECUTED", "REUSED_FROM_COMBINED_CALL", "DETERMINISTIC_ONLY"],
                "NEGATIVE_OR_NON_HISTORICAL": ["LLM_CALL_EXECUTED", "NOT_REQUIRED", "DETERMINISTIC_ONLY"],
                "COMPLEX": ["LLM_CALL_EXECUTED", "DETERMINISTIC_ONLY"],
            },
            "maximum_parallel_model_requests": 1,
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, payload in sorted(reports.items()):
        atomic_write_json(output / filename, payload)
    atomic_write_text(
        output / "architecture-report.md",
        _architecture_report(pilot_manifest),
    )
    atomic_write_text(
        output / "ollama-arabic-integration-report.md",
        _ollama_arabic_integration_report(),
    )
    return {
        "status": "VALID_FOUNDATION_PENDING_REAL_MODEL",
        "pilot_id": pilot_id,
        "sample_count": len(pilot),
        "output_root": str(output),
        "model_downloaded": False,
        "model_executed": False,
    }


def _architecture_report(pilot: dict[str, Any]) -> str:
    categories = sorted(
        {
            reason
            for item in pilot["segments"]
            for reason in item["selection_reasons"]
        }
    )
    return f"""# Siraj Local Semantic Intelligence Foundation

## Current gaps

- Rule extraction is retained as a candidate baseline, not semantic truth.
- Human Gold review diagnoses boundary, typing, event, relation, temporal,
  isnad, and attribution failures.
- No local semantic model has been qualified or executed by this foundation.

## Reused contracts

- Shamela ingestion provenance, immutable locators, source IDs, and original text.
- Historical extraction candidates and quality-audit reviewer notes.
- Deterministic IDs, canonical timestamps, hashes, and atomic checkpoints.
- Existing provider isolation and local-only security conventions.

## Adapter boundary

`SemanticExtractionProvider` is provider-neutral. `OllamaLocalSemanticProvider`
contains all Ollama HTTP details and accepts an explicit model reference. Domain,
Gold, ingestion, and graph layers do not import the adapter.

## Dependency direction

Gold/provenance input -> semantic orchestrator -> provider abstraction ->
Ollama loopback adapter. Deterministic validation and reconciliation consume
provider output. There is no Knowledge Graph dependency or write path.

## Security boundary

- LOCAL_ONLY accepts `http://127.0.0.1`, `http://localhost`, or loopback IPv6.
- Source text is serialized as untrusted data under a versioned prompt contract.
- No telemetry, cloud fallback, model download, credentials, or public prompt logs.
- One model and one segment are processed sequentially.

## Lifecycle

STRUCTURAL_ANALYSIS -> MENTION_EXTRACTION -> EVENT_RELATION_EXTRACTION ->
CLAIM_ATTRIBUTION -> DETERMINISTIC_EVIDENCE_VALIDATION -> CRITICAL_REVIEW ->
RECONCILIATION -> LEARNING_REPORT.

Non-historical segments short-circuit model extraction. Isnad, poetry,
biography, and historical narrative receive explicit routes. Every stage is
checkpointed and may resume only when its canonical input hash matches.

## Pilot and test matrix

- Pilot count: {pilot['sample_count']}
- Categories: {', '.join(categories)}
- Unit and integration tests use only a deterministic fake provider.
- Ollama absence, schema errors, evidence mismatch, interrupted stages,
  cache determinism, unload, loopback policy, and CLI failure mapping are tested.

## Explicit exclusions

No Gold labels are edited, no Shamela installation path is accessed, no corpus
is expanded, no graph is built, and no media pipeline is started.
"""


def load_provider_config(path: str | Path) -> OllamaLocalSemanticConfig:
    payload = _read_json(Path(path))
    provider = payload.get("provider", {})
    hardware = payload.get("hardware", {})
    return OllamaLocalSemanticConfig(
        endpoint=str(provider.get("endpoint", "http://127.0.0.1:11434")),
        model_reference=str(provider.get("model_reference", "")),
        model_digest=str(provider.get("model_digest", "UNRESOLVED")),
        profile=str(provider.get("profile", "LOCAL_ONLY")),
        model_policy=str(provider.get("model_policy", "PILOT_MODEL_ONLY")),
        connect_timeout_seconds=float(provider.get("connect_timeout_seconds", provider.get("timeout_seconds", 10))),
        model_load_timeout_seconds=float(provider.get("model_load_timeout_seconds", 300)),
        generation_timeout_seconds=float(provider.get("generation_timeout_seconds", provider.get("timeout_seconds", 900))),
        overall_stage_timeout_seconds=float(provider.get("overall_stage_timeout_seconds", 900)),
        retries=int(provider.get("retries", 1)),
        stream=False,
        temperature=0.0,
        thinking=bool(provider.get("thinking", False)),
        raw_response_retention=str(provider.get("raw_response_retention", "SAFE_LOCAL_ARTIFACT")),
        hardware=SemanticHardwareProfile(
            concurrency=int(hardware.get("concurrency", 1)),
            context_tokens=int(hardware.get("context_tokens", 1536)),
            maximum_output_tokens=int(
                hardware.get("maximum_output_tokens", 700)
            ),
            stage_timeout_seconds=float(
                hardware.get("stage_timeout_seconds", 900)
            ),
            keep_alive=str(hardware.get("keep_alive", "10m")),
            checkpoint_after_each_stage=bool(
                hardware.get("checkpoint_after_each_stage", True)
            ),
        ),
    )


def semantic_status(
    output_root: str | Path,
    provider: SemanticExtractionProvider,
) -> dict[str, Any]:
    root = Path(output_root).resolve()
    health = provider.health_check()
    pilot = _read_json(root / "pilot-12-manifest.json")
    completed = len(list((root / "segments").glob("*/run-summary.json")))
    return {
        "status": health.status,
        "reason_code": health.reason_code,
        "provider": asdict(health.provider),
        "localhost_only": health.localhost_only,
        "pilot_count": pilot["sample_count"],
        "completed_segments": completed,
        "pending_segments": pilot["sample_count"] - completed,
        "knowledge_graph_written": False,
    }


def _load_segment(output_root: Path, audit_segment_id: str) -> SemanticSegmentInput:
    payload = _read_json(
        output_root / "segments" / audit_segment_id / "segment-input.json"
    )
    return SemanticSegmentInput(
        **{
            key: payload[key]
            for key in (
                "audit_segment_id",
                "source_id",
                "locator",
                "original_text",
                "book_id",
                "book_title",
                "segment_id",
                "current_extraction",
                "reviewer_notes",
                "selection_reasons",
            )
        }
    )


def run_semantic_segment(
    output_root: str | Path,
    provider: SemanticExtractionProvider,
    audit_segment_id: str,
) -> dict[str, Any]:
    root = Path(output_root).resolve()
    segment = _load_segment(root, audit_segment_id)
    if (
        getattr(provider, "identity", None)
        and provider.identity.provider_id == "OLLAMA_LOCAL_SEMANTIC"
    ):
        health = provider.health_check()
        if health.status != "AVAILABLE":
            raise SemanticProviderError(health.reason_code)
    try:
        result = LocalSemanticOrchestrator(provider, root).run_segment(segment)
    except RuntimeError as error:
        if getattr(provider, "identity", None) and provider.identity.provider_id == "OLLAMA_LOCAL_SEMANTIC":
            _record_real_model_failure(root, segment, provider, str(error))
        raise
    if getattr(provider, "identity", None) and provider.identity.provider_id == "OLLAMA_LOCAL_SEMANTIC":
        _record_real_model_single_segment(root, segment, result)
    return result


def _record_real_model_failure(
    root: Path,
    segment: SemanticSegmentInput,
    provider: SemanticExtractionProvider,
    error: str,
) -> None:
    payload = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "status": "REAL_MODEL_SINGLE_SEGMENT_BLOCKED",
        "audit_segment_id": segment.audit_segment_id,
        "provider": asdict(provider.identity),
        "model_policy": "PILOT_MODEL_ONLY",
        "blocker": error,
        "checkpoint_root": str(root / "segments" / segment.audit_segment_id),
        "knowledge_graph_written": False,
    }
    atomic_write_json(root / "real-model-single-segment-run.json", payload)
    atomic_write_text(
        root / "ollama-arabic-integration-report.md",
        _ollama_arabic_integration_report(
            status="REAL_MODEL_SINGLE_SEGMENT_BLOCKED",
        ) + "\n## Blocker\n\n`" + error + "`\n",
    )


def _stage_payload(root: Path, audit_segment_id: str, filename: str) -> dict[str, Any]:
    return _read_json(root / "segments" / audit_segment_id / filename)


def _record_real_model_single_segment(
    root: Path,
    segment: SemanticSegmentInput,
    summary: dict[str, Any],
) -> None:
    validation = _stage_payload(
        root,
        segment.audit_segment_id,
        "05-deterministic_evidence_validation.json",
    )
    reconciliation = _stage_payload(
        root,
        segment.audit_segment_id,
        "07-reconciliation.json",
    )
    learning = _stage_payload(
        root,
        segment.audit_segment_id,
        "08-learning_report.json",
    )
    status = (
        "VALID_REAL_MODEL_SINGLE_SEGMENT_PENDING_PILOT_12"
        if validation["payload"].get("status") == "VALID"
        else "REAL_MODEL_SINGLE_SEGMENT_REQUIRES_REVIEW"
    )
    common = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "status": status,
        "audit_segment_id": segment.audit_segment_id,
        "run_id": summary["run_id"],
        "provider": summary["provider"],
        "model_policy": "PILOT_MODEL_ONLY",
        "prompt_version": summary["provider"]["prompt_version"],
        "original_text_hash": summary["original_text_hash"],
        "baseline_hash": summary["baseline_hash"],
        "reviewer_notes_role": "HUMAN_DIAGNOSTIC_CONTEXT_ONLY",
        "knowledge_graph_written": False,
    }
    atomic_write_json(
        root / "real-model-single-segment-run.json",
        {**common, "summary": summary},
    )
    atomic_write_json(
        root / "real-model-performance-report.json",
        {
            **common,
            "total_stage_latency_ms": summary["total_stage_latency_ms"],
            "model_load_time_ms": summary["model_load_time_ms"],
            "tokens": summary["tokens"],
            "one_model_request_at_a_time": True,
        },
    )
    atomic_write_json(
        root / "real-model-validation-report.json",
        {**common, **validation["payload"]},
    )
    atomic_write_json(
        root / "real-model-reconciliation-report.json",
        {**common, **reconciliation["payload"]},
    )
    atomic_write_json(
        root / "real-model-learning-report.json",
        {**common, **learning["payload"]},
    )
    atomic_write_text(
        root / "ollama-arabic-integration-report.md",
        _ollama_arabic_integration_report(
            status=status,
            real_result=summary,
        ),
    )


def _ollama_arabic_integration_report(
    *,
    status: str = "IMPLEMENTED_PENDING_REAL_MODEL_RUN",
    real_result: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# Ollama Arabic Integration Report",
        "",
        f"- Status: `{status}`",
        "- Endpoint: `http://127.0.0.1:11434/api/chat`",
        "- Transport: canonical UTF-8 bytes without BOM",
        "- Content-Type: `application/json; charset=utf-8`",
        "- Structured output: stage-specific complete JSON Schema through `format`",
        "- Model reference: `qwen3:4b-instruct` (`PILOT_MODEL_ONLY`)",
        "- Concurrency: one model request at a time",
        "- Context target: 1536; keep-alive: 10m; generation timeout: 900s",
        "- Retry policy: one explicit retry only for retryable local failures",
        "",
        "## Previous timeout cause",
        "",
        "The prior adapter used `/api/generate` and one shared 120-second timeout. "
        "Model load, connection, and generation were not represented separately, "
        "and a mandatory multi-stage route could multiply the time spent per segment.",
        "",
        "## Current safeguards",
        "",
        "- Loopback-only endpoint validation.",
        "- UTF-8 request serialization and corrupted `???` Arabic-output rejection.",
        "- Separate connect, model-load, generation, and stage timeout metadata.",
        "- Safe response headers only; no credentials or prompt text in logs.",
        "- Local safe raw response artifacts contain response data only, never credentials.",
        "- No cloud fallback, automatic model download, graph write, or Gold-label use.",
    ]
    if real_result:
        lines.extend(
            [
                "",
                "## Real single-segment result",
                "",
                f"- Run ID: `{real_result['run_id']}`",
                f"- Execution plan: `{real_result['execution_plan']}`",
                f"- Stage latency ms: `{real_result['total_stage_latency_ms']}`",
                f"- Model load ms: `{real_result['model_load_time_ms']}`",
                f"- Tokens: `{real_result['tokens']}`",
            ]
        )
    return "\n".join(lines) + "\n"


def benchmark_pilot(
    output_root: str | Path,
    provider: SemanticExtractionProvider,
    *,
    sample: str = "pilot-12",
) -> dict[str, Any]:
    if sample != "pilot-12":
        raise ValueError("ONLY_PILOT_12_IS_ALLOWED")
    root = Path(output_root).resolve()
    pilot = _read_json(root / "pilot-12-manifest.json")
    summaries = [
        run_semantic_segment(root, provider, item["audit_segment_id"])
        for item in pilot["segments"]
    ]
    report = compare_semantic_runs(root)
    manifest = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "status": "COMPLETED",
        "pilot_id": pilot["pilot_id"],
        "sample": sample,
        "provider": asdict(provider.identity),
        "segment_run_ids": sorted(item["run_id"] for item in summaries),
        "segment_count": len(summaries),
        "cache_hits": sum(item["cache_hits"] for item in summaries),
        "total_stage_latency_ms": round(
            sum(item["total_stage_latency_ms"] for item in summaries),
            3,
        ),
        "model_load_time_ms": round(
            sum(item["model_load_time_ms"] for item in summaries),
            3,
        ),
        "tokens": {
            key: sum(item.get("tokens", {}).get(key, 0) for item in summaries)
            for key in sorted(
                {
                    key
                    for item in summaries
                    for key in item.get("tokens", {})
                }
            )
        },
        "comparison_hash": integrity_hash(report),
        "execution_policy": "SEQUENTIAL_ONE_MODEL_ONE_SEGMENT",
    }
    atomic_write_json(root / "benchmark-run-manifest.json", manifest)
    return manifest


def compare_semantic_runs(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root).resolve()
    summaries = [
        _read_json(path)
        for path in sorted((root / "segments").glob("*/run-summary.json"))
    ]
    aggregate = {
        status: sum(
            int(item["reconciliation_counts"].get(status, 0))
            for item in summaries
        )
        for status in (
            "ACCEPTED_HIGH_CONFIDENCE",
            "ACCEPTED_WITH_WARNING",
            "HUMAN_REVIEW_REQUIRED",
            "REJECTED_UNSUPPORTED",
        )
    }
    report = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "status": "COMPLETED" if summaries else "PENDING_PILOT_EXECUTION",
        "completed_segments": len(summaries),
        "counts": aggregate,
        "run_ids": sorted(item["run_id"] for item in summaries),
        "baseline_role": "CANDIDATE_GENERATOR_AND_COMPARISON_BASELINE",
        "graph_written": False,
    }
    atomic_write_json(root / "reconciliation-report.json", report)
    learning_items = []
    for path in sorted((root / "segments").glob("*/08-learning_report.json")):
        learning_items.append(_read_json(path)["payload"])
    atomic_write_json(
        root / "learning-report.json",
        {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "status": report["status"],
            "segments": learning_items,
            "automatic_rule_changes_allowed": False,
        },
    )
    atomic_write_json(
        root / "performance-report.json",
        {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "status": report["status"],
            "segment_count": len(summaries),
            "cache_hits": sum(item.get("cache_hits", 0) for item in summaries),
            "total_stage_latency_ms": round(
                sum(item.get("total_stage_latency_ms", 0) for item in summaries),
                3,
            ),
            "model_load_time_ms": round(
                sum(item.get("model_load_time_ms", 0) for item in summaries),
                3,
            ),
            "tokens": {
                key: sum(
                    item.get("tokens", {}).get(key, 0)
                    for item in summaries
                )
                for key in sorted(
                    {
                        key
                        for item in summaries
                        for key in item.get("tokens", {})
                    }
                )
            },
            "deterministic_run_hash": integrity_hash(summaries),
            "peak_memory": "NOT_MEASURED_PORTABLY",
            "wall_clock_is_not_a_correctness_gate": True,
        },
    )
    return report


def build_ollama_provider(
    config_path: str | Path,
    *,
    transport: Callable[..., dict[str, Any]] | None = None,
) -> OllamaLocalSemanticProvider:
    return OllamaLocalSemanticProvider(
        load_provider_config(config_path),
        transport=transport,
    )


__all__ = [
    "FOUNDATION_VERSION",
    "PILOT_SIZE",
    "benchmark_pilot",
    "build_ollama_provider",
    "compare_semantic_runs",
    "initialize_semantic_foundation",
    "load_provider_config",
    "run_semantic_segment",
    "select_pilot_12",
    "semantic_status",
]
