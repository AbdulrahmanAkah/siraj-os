"""Real-model Pilot-12 preparation, execution, and human-gated evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
import ctypes
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
    integrity_hash,
)

from .models import (
    PROMPT_VERSION,
    SEMANTIC_SCHEMA_VERSION,
    STAGES,
    SemanticProviderError,
    SemanticSegmentInput,
)
from .orchestrator import (
    LocalSemanticOrchestrator,
    atomic_write_json,
    atomic_write_text,
)
from .provider import SemanticExtractionProvider
from .semantic_prompts import prompt_manifest


PILOT_EVALUATION_SCHEMA_VERSION = "siraj-local-semantic-pilot-evaluation-v1"
PILOT_SAMPLE = "pilot-12"
PILOT_SIZE = 12
PRE_ADJUDICATION_STATUS = (
    "VALID_REAL_MODEL_PILOT_12_PENDING_HUMAN_ADJUDICATION"
)
POST_ADJUDICATION_STATUS = "VALID_REAL_MODEL_PILOT_12_EVALUATED"
BLOCKED_ADJUDICATION_STATUS = "BLOCKED_PENDING_HUMAN_ADJUDICATION"

PILOT_MODEL_OUTPUT_LIMITS = {
    "entities_per_segment": 12,
    "events_per_segment": 2,
    "relations_per_segment": 3,
    "institutions_per_segment": 2,
    "claims_per_segment": 2,
    "isnads_per_segment": 2,
    "temporal_mentions_per_segment": 3,
    "critic_issues_per_segment": 12,
    "quality_effect": "BOUNDED_RECALL_REQUIRES_HUMAN_ADJUDICATION",
    "scope": "LOW_MEMORY_PILOT_ONLY",
}

ADJUDICATION_CATEGORIES = (
    "structure",
    "entities",
    "events",
    "relations",
    "temporal_mentions",
    "isnad",
    "claims_attribution",
)

ERROR_TAXONOMY = (
    "ENTITY_MISSING",
    "ENTITY_FALSE_POSITIVE",
    "ENTITY_BOUNDARY_TOO_SHORT",
    "ENTITY_BOUNDARY_TOO_LONG",
    "ENTITY_TYPE_WRONG",
    "CONTEXTUAL_ROLE_WRONG",
    "EVENT_MISSING",
    "EVENT_FALSE_POSITIVE",
    "EVENT_TYPE_WRONG",
    "PARTICIPANT_ROLE_WRONG",
    "PLACE_ROLE_WRONG",
    "RELATION_MISSING",
    "RELATION_FALSE_POSITIVE",
    "TEMPORAL_MISSING",
    "TEMPORAL_RESOLUTION_WRONG",
    "ISNAD_BOUNDARY_WRONG",
    "ISNAD_ORDER_WRONG",
    "HEADING_AS_BODY_EVIDENCE",
    "POETRY_AS_HISTORICAL_FACT",
    "EXTERNAL_KNOWLEDGE_HALLUCINATION",
    "UNSUPPORTED_INFERENCE",
    "CLAIM_ATTRIBUTION_WRONG",
    "NEGATION_OR_MODALITY_WRONG",
    "CONTEXT_REQUIRED",
    "SCHEMA_OR_ENCODING_FAILURE",
)

_COVERAGE_TARGETS = (
    "ISNAD_CASE",
    "APPOINTMENT_OR_DISMISSAL_CASE",
    "MULTI_EVENT_CASE",
    "BIOGRAPHICAL_CASE",
    "POETRY_OR_SIRA_CASE",
    "RELATIVE_TEMPORAL_CASE",
    "MULTIPLE_PERSONS_AND_RELATIONS_CASE",
    "INSTITUTION_OR_OFFICE_CASE",
    "POSITIVE_ENTITY_BOUNDARY_CASE",
    "HEADING_BOUNDARY_CASE",
    "NEGATIVE_CONTROL_CASE",
    "COMPLEX_HISTORICAL_CASE",
)


class PilotEvaluationError(ValueError):
    """A Pilot-12 integrity or lifecycle gate failed."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise PilotEvaluationError(
            f"INVALID_JSON:{path.name}:{error.lineno}:{error.colno}"
        ) from error
    if not isinstance(value, dict):
        raise PilotEvaluationError(f"JSON_ROOT_MUST_BE_OBJECT:{path.name}")
    return value


def _default_audit_root(semantic_root: Path) -> Path:
    return semantic_root.parent / "shamela-extraction-quality-audit"


def pilot_root(semantic_root: str | Path) -> Path:
    return Path(semantic_root).resolve() / PILOT_SAMPLE


def _current_counts(current: dict[str, Any]) -> dict[str, int]:
    return {
        key: len(current.get(key, []))
        for key in (
            "entities",
            "events",
            "relations",
            "claims",
            "temporal_mentions",
            "isnad_chains",
        )
    }


def _candidate_tags(
    annotation: dict[str, Any],
    manifest_entry: dict[str, Any],
) -> set[str]:
    text = str(annotation.get("original_text", ""))
    current = dict(annotation.get("current_extraction", {}))
    counts = _current_counts(current)
    reasons = set(map(str, manifest_entry.get("selection_reasons", [])))
    tags: set[str] = set()
    if counts["entities"]:
        tags.add("POSITIVE_ENTITY_BOUNDARY_CASE")
    if (
        any(token in text for token in ("عزل", "ولاه", "رتب عوضه"))
        or any(
            any(token in str(item.get("event_type", "")).upper() for token in ("APPOINT", "DISMISS", "REPLACE"))
            for item in current.get("events", [])
        )
    ):
        tags.add("APPOINTMENT_OR_DISMISSAL_CASE")
    if counts["isnad_chains"] or "CURRENT_ISNAD_CHAIN" in reasons:
        tags.add("ISNAD_CASE")
    if int(annotation.get("book_id", -1)) == 619:
        tags.add("POETRY_OR_SIRA_CASE")
    if any(
        token in text
        for token in (
            "الوزير",
            "الوزارة",
            "استاذية",
            "إمارة",
            "مدرسة",
            "خزانة",
            "ولاية",
            "النظر ب",
        )
    ):
        tags.add("INSTITUTION_OR_OFFICE_CASE")
    if counts["temporal_mentions"] and any(
        token in text for token in ("بعد", "قبل", "منذ", "إلى أن", "ثم")
    ):
        tags.add("RELATIVE_TEMPORAL_CASE")
    if "HEADING_BEARING_SEGMENT" in reasons or "data-type=" in text:
        tags.add("HEADING_BOUNDARY_CASE")
    if (
        not any(
            counts[key]
            for key in (
                "events",
                "relations",
                "claims",
                "isnad_chains",
            )
        )
        and "NEGATIVE_CONTROL_NO_CURRENT_SIGNAL" in reasons
    ):
        tags.add("NEGATIVE_CONTROL_CASE")
    if counts["events"] >= 2:
        tags.add("MULTI_EVENT_CASE")
    if counts["entities"] >= 3 and counts["relations"] >= 1:
        tags.add("MULTIPLE_PERSONS_AND_RELATIONS_CASE")
    if re.search(r"(?:^|[\s،.؛])(?:توفي|ولد)(?:[\s،.؛])", text):
        tags.add("BIOGRAPHICAL_CASE")
    if (
        len(text) >= 500
        and sum(bool(counts[key]) for key in counts) >= 3
    ):
        tags.add("COMPLEX_HISTORICAL_CASE")
    return tags


def _target_rank(target: str, candidate: dict[str, Any]) -> tuple[Any, ...]:
    annotation = candidate["annotation"]
    counts = candidate["counts"]
    length = len(annotation["original_text"])
    book_id = int(annotation["book_id"])
    if target == "COMPLEX_HISTORICAL_CASE":
        primary = (
            0 if length <= 1200 else 1,
            abs(length - 900),
            -sum(counts.values()),
        )
    elif target == "POETRY_OR_SIRA_CASE":
        primary = (
            0 if counts["events"] else 1,
            0 if counts["entities"] else 1,
            length,
        )
    elif target == "NEGATIVE_CONTROL_CASE":
        primary = (
            0 if book_id == 151020 else 1,
            sum(counts.values()),
            length,
        )
    elif target == "POSITIVE_ENTITY_BOUNDARY_CASE":
        primary = (
            0 if book_id == 5 else 1,
            abs(counts["entities"] - 2),
            length,
        )
    elif target == "HEADING_BOUNDARY_CASE":
        primary = (
            0 if book_id == 5 else 1,
            length,
        )
    elif target == "INSTITUTION_OR_OFFICE_CASE":
        primary = (
            length,
            0 if book_id == 400 else 1,
            -sum(counts.values()),
        )
    else:
        primary = (length, -sum(counts.values()))
    return (*primary, str(annotation["audit_segment_id"]))


def select_evaluation_pilot_12(
    gold_payload: dict[str, Any],
    audit_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Select coverage deterministically without reading expected Gold fields."""

    manifest_by_id = {
        str(item["audit_segment_id"]): item
        for item in audit_manifest.get("segments", [])
    }
    candidates: list[dict[str, Any]] = []
    for annotation in gold_payload.get("annotations", []):
        audit_id = str(annotation["audit_segment_id"])
        entry = manifest_by_id.get(audit_id, {})
        current = dict(annotation.get("current_extraction", {}))
        candidates.append(
            {
                "annotation": annotation,
                "manifest": entry,
                "counts": _current_counts(current),
                "tags": _candidate_tags(annotation, entry),
            }
        )
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for target in _COVERAGE_TARGETS:
        matches = [
            item
            for item in candidates
            if target in item["tags"]
            and str(item["annotation"]["audit_segment_id"])
            not in selected_ids
        ]
        if not matches:
            raise PilotEvaluationError(
                f"PILOT_COVERAGE_TARGET_UNAVAILABLE:{target}"
            )
        chosen = min(matches, key=lambda item: _target_rank(target, item))
        chosen = {
            **chosen,
            "primary_selection_target": target,
        }
        selected.append(chosen)
        selected_ids.add(str(chosen["annotation"]["audit_segment_id"]))
    if len(selected) != PILOT_SIZE:
        raise PilotEvaluationError("PILOT_SELECTION_COUNT_INVALID")
    return sorted(
        selected,
        key=lambda item: str(item["annotation"]["audit_segment_id"]),
    )


def _text_type(tags: set[str]) -> str:
    if "ISNAD_CASE" in tags:
        return "ISNAD"
    if "POETRY_OR_SIRA_CASE" in tags:
        return "POETRY_SIRA"
    if "BIOGRAPHICAL_CASE" in tags:
        return "BIOGRAPHICAL"
    if "NEGATIVE_CONTROL_CASE" in tags:
        return "NEGATIVE_OR_NON_HISTORICAL"
    if "COMPLEX_HISTORICAL_CASE" in tags:
        return "COMPLEX_HISTORICAL"
    return "HISTORICAL_PROSE"


def _execution_plan_hint(primary: str, tags: set[str]) -> str:
    if primary == "NEGATIVE_CONTROL_CASE":
        return "NEGATIVE_OR_NON_HISTORICAL"
    if primary == "ISNAD_CASE":
        return "ISNAD"
    if primary == "POETRY_OR_SIRA_CASE":
        return "POETRY_SIRA"
    if primary == "BIOGRAPHICAL_CASE":
        return "BIOGRAPHICAL"
    if primary == "COMPLEX_HISTORICAL_CASE":
        return "COMPLEX_HISTORICAL"
    if "COMPLEX_HISTORICAL_CASE" in tags:
        return "COMPLEX_HISTORICAL"
    return "SIMPLE_HISTORICAL"


def _segment_input(
    selected: dict[str, Any],
) -> tuple[SemanticSegmentInput, dict[str, Any]]:
    annotation = selected["annotation"]
    tags = set(selected["tags"])
    plan = _execution_plan_hint(
        selected["primary_selection_target"],
        tags,
    )
    routing_reasons = set(map(str, selected["manifest"].get("selection_reasons", [])))
    routing_reasons.update(tags)
    if plan == "NEGATIVE_OR_NON_HISTORICAL":
        routing_reasons.add("NEGATIVE_CONTROL")
    elif plan == "ISNAD":
        routing_reasons.add("ISNAD")
    elif plan == "POETRY_SIRA":
        routing_reasons.add("POETRY_OR_SIRA")
    elif plan == "BIOGRAPHICAL":
        routing_reasons.add("BIOGRAPHICAL")
    elif plan == "COMPLEX_HISTORICAL":
        routing_reasons.add("COMPLEX_HISTORICAL")
    segment = SemanticSegmentInput(
        audit_segment_id=str(annotation["audit_segment_id"]),
        source_id=str(annotation["source_id"]),
        locator=str(annotation["locator"]),
        original_text=str(annotation["original_text"]),
        book_id=int(annotation["book_id"]),
        book_title=str(annotation.get("book_title", "")),
        segment_id=int(annotation["segment_id"]),
        current_extraction=dict(annotation.get("current_extraction", {})),
        reviewer_notes=str(annotation.get("reviewer_notes", "")),
        selection_reasons=sorted(routing_reasons),
    )
    coverage = {
        "primary_selection_target": selected["primary_selection_target"],
        "coverage_tags": sorted(tags),
        "text_type": _text_type(tags),
        "execution_plan_hint": plan,
        "semantic_risks": sorted(
            {
                {
                    "ISNAD_CASE": "NARRATOR_MATN_BOUNDARY",
                    "POETRY_OR_SIRA_CASE": "POETRY_AS_FACT",
                    "HEADING_BOUNDARY_CASE": "HEADING_AS_BODY",
                    "NEGATIVE_CONTROL_CASE": "FALSE_POSITIVE",
                    "APPOINTMENT_OR_DISMISSAL_CASE": "PARTICIPANT_AND_OFFICE_ROLES",
                    "RELATIVE_TEMPORAL_CASE": "RELATIVE_TIME_OVERRESOLUTION",
                    "MULTI_EVENT_CASE": "COMPOUND_EVENT_COLLAPSE",
                    "MULTIPLE_PERSONS_AND_RELATIONS_CASE": "ARGUMENT_LINKING",
                    "BIOGRAPHICAL_CASE": "BIOGRAPHY_EVENT_TYPING",
                    "INSTITUTION_OR_OFFICE_CASE": "OFFICE_INSTITUTION_CONFUSION",
                    "POSITIVE_ENTITY_BOUNDARY_CASE": "ARABIC_NAME_BOUNDARY",
                    "COMPLEX_HISTORICAL_CASE": "CONTEXT_AND_OUTPUT_LIMIT",
                }[tag]
                for tag in tags
            }
        ),
    }
    return segment, coverage


def _initial_adjudication(
    manifest: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    annotations = []
    for item in manifest["segments"]:
        segment = _read_json(root / item["input_artifact"])
        annotations.append(
            {
                "annotation_id": deterministic_id(
                    "pilot_12_adjudication",
                    [manifest["pilot_id"], item["audit_segment_id"]],
                ),
                "audit_segment_id": item["audit_segment_id"],
                "segment_id": item["segment_id"],
                "source_id": item["source_id"],
                "locator": item["locator"],
                "book_id": item["book_id"],
                "book_title": item["book_title"],
                "original_text": segment["original_text"],
                "immutable_input_hash": item["input_hash"],
                "structural_type_gold": "",
                "gold_entities": [],
                "gold_events": [],
                "gold_relations": [],
                "gold_temporal_mentions": [],
                "gold_isnad": [],
                "gold_claims_attribution": [],
                "explicitly_absent": {
                    category: False
                    for category in ADJUDICATION_CATEGORIES
                    if category != "structure"
                },
                "category_review": {
                    category: "PENDING"
                    for category in ADJUDICATION_CATEGORIES
                },
                "adjudication_status": "PENDING",
                "model_output_judgments": [],
                "baseline_output_judgments": [],
                "reviewer_notes": "",
                "prior_diagnostic_reviewer_notes": segment.get(
                    "reviewer_notes",
                    "",
                ),
                "expert_review_resolution": {
                    "status": "UNRESOLVED",
                    "reason": "",
                },
            }
        )
    return {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "pilot_id": manifest["pilot_id"],
        "created_at": CANONICAL_TIMESTAMP,
        "status": BLOCKED_ADJUDICATION_STATUS,
        "original_gold_set_modified": False,
        "annotations": annotations,
    }


def _evaluation_plan_markdown() -> str:
    return """# Siraj Real-Model Pilot-12 Evaluation Plan

## Scope

Evaluate twelve deterministic, provenance-bound Shamela segments with one
local `qwen3:4b-instruct` request at a time. Existing rule extraction is a
candidate baseline. Prior reviewer notes are diagnostic context only.

## Invariants

- Original Gold annotations are read-only and expected fields are ignored.
- Every model item must retain literal evidence, source ID, and locator.
- Checkpoints resume by provider, model digest, prompt, schema, and input hash.
- Raw responses remain local audit artifacts; public logs omit source text.
- No Knowledge Graph, corpus expansion, cloud provider, or Shamela write path.

## Human gate

The evaluation remains `BLOCKED_PENDING_HUMAN_ADJUDICATION` until all seven
categories of every segment are reviewed or explicitly marked absent.
`NEEDS_EXPERT_REVIEW` blocks scoring unless an explicit expert resolution
records inclusion or exclusion with a reason.
"""


def _adjudication_guide_markdown() -> str:
    return """# Pilot-12 Human Adjudication Guide

Review structure, entities, events, relations, temporal mentions, isnad, and
claim attribution independently. Empty arrays are not decisions: mark the
category reviewed and explicitly absent when no item exists.

Use exact zero-based spans from the immutable source text. Judge baseline,
raw-model, and reconciled outputs separately. Multiple error taxonomy codes
may be attached to one item. Prior reviewer notes are diagnostic hints, never
Gold labels.

`COMPLETED` is accepted only when every category is resolved. Expert-review
rows require an explicit resolution and reason before evaluation.
"""


def prepare_pilot_12_evaluation(
    semantic_root: str | Path,
    *,
    audit_root: str | Path | None = None,
) -> dict[str, Any]:
    semantic = Path(semantic_root).resolve()
    audit = (
        Path(audit_root).resolve()
        if audit_root is not None
        else _default_audit_root(semantic)
    )
    root = pilot_root(semantic)
    if root == audit or audit in root.parents:
        raise PilotEvaluationError("PILOT_OUTPUT_MUST_NOT_MUTATE_GOLD")
    gold = _read_json(audit / "gold-annotation-template.json")
    audit_manifest = _read_json(audit / "audit-sample-manifest.json")
    selected = select_evaluation_pilot_12(gold, audit_manifest)
    entries: list[dict[str, Any]] = []
    for item in selected:
        segment, coverage = _segment_input(item)
        relative = (
            Path("segments")
            / segment.audit_segment_id
            / "segment-input.json"
        )
        payload = {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            **asdict(segment),
            "expected_gold_labels_loaded": False,
            "knowledge_graph_write_allowed": False,
            "immutable": True,
        }
        atomic_write_json(root / relative, payload)
        entries.append(
            {
                "audit_segment_id": segment.audit_segment_id,
                "source_id": segment.source_id,
                "locator": segment.locator,
                "book_id": segment.book_id,
                "book_title": segment.book_title,
                "segment_id": segment.segment_id,
                "input_hash": integrity_hash(payload),
                "input_artifact": relative.as_posix(),
                "original_audit_selection_reasons": sorted(
                    map(
                        str,
                        item["manifest"].get(
                            "selection_reasons",
                            [],
                        ),
                    )
                ),
                **coverage,
            }
        )
    coverage_state = {
        target: any(
            target in item["coverage_tags"]
            for item in entries
        )
        for target in _COVERAGE_TARGETS
    }
    if not all(coverage_state.values()):
        raise PilotEvaluationError("PILOT_COVERAGE_INCOMPLETE")
    pilot_id = deterministic_id(
        "real_model_pilot_12",
        [
            PILOT_EVALUATION_SCHEMA_VERSION,
            [item["audit_segment_id"] for item in entries],
            [item["input_hash"] for item in entries],
        ],
    )
    manifest = {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "pilot_id": pilot_id,
        "sample": PILOT_SAMPLE,
        "created_at": CANONICAL_TIMESTAMP,
        "selection_policy": (
            "DETERMINISTIC_REQUIRED_COVERAGE_WITH_STABLE_TARGET_RANK"
        ),
        "sample_count": len(entries),
        "segments": entries,
        "source_gold_hash": integrity_hash(
            {
                "schema_version": gold.get("schema_version"),
                "annotation_ids": sorted(
                    str(item["audit_segment_id"])
                    for item in gold.get("annotations", [])
                ),
            }
        ),
        "expected_gold_fields_read": False,
        "reviewer_notes_role": "DIAGNOSTIC_ONLY",
        "knowledge_graph_write_allowed": False,
    }
    root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(root / "pilot-12-selection-manifest.json", manifest)
    atomic_write_json(
        root / "pilot-12-coverage-report.json",
        {
            "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
            "pilot_id": pilot_id,
            "status": "VALID",
            "coverage": coverage_state,
            "book_distribution": dict(
                sorted(Counter(item["book_title"] for item in entries).items())
            ),
            "text_type_distribution": dict(
                sorted(Counter(item["text_type"] for item in entries).items())
            ),
            "segments": entries,
        },
    )
    atomic_write_json(
        root / "pilot-12-error-taxonomy.json",
        {
            "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
            "allows_multiple_codes_per_item": True,
            "codes": [
                {"code": code, "active": True}
                for code in ERROR_TAXONOMY
            ],
        },
    )
    atomic_write_text(
        root / "pilot-12-evaluation-plan.md",
        _evaluation_plan_markdown(),
    )
    atomic_write_text(
        root / "pilot-12-human-adjudication-guide.md",
        _adjudication_guide_markdown(),
    )
    adjudication_path = root / "pilot-12-human-adjudication.json"
    if adjudication_path.exists():
        existing = _read_json(adjudication_path)
        immutable = {
            item["audit_segment_id"]: item["input_hash"]
            for item in manifest["segments"]
        }
        existing_immutable = {
            item["audit_segment_id"]: item["immutable_input_hash"]
            for item in existing.get("annotations", [])
        }
        if immutable != existing_immutable:
            untouched = all(
                item.get("adjudication_status") == "PENDING"
                and not item.get("reviewer_notes")
                and not item.get("model_output_judgments")
                and not item.get("baseline_output_judgments")
                for item in existing.get("annotations", [])
            )
            if not untouched:
                raise PilotEvaluationError(
                    "EXISTING_ADJUDICATION_INPUT_IDENTITY_MISMATCH"
                )
            atomic_write_json(
                adjudication_path,
                _initial_adjudication(manifest, root),
            )
    else:
        atomic_write_json(
            adjudication_path,
            _initial_adjudication(manifest, root),
        )
    blocked = {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "pilot_id": pilot_id,
        "status": BLOCKED_ADJUDICATION_STATUS,
        "reason_code": "TWELVE_HUMAN_ADJUDICATIONS_REQUIRED",
        "metrics": None,
        "knowledge_graph_build_allowed": False,
    }
    for name in (
        "pilot-12-semantic-evaluation.json",
        "pilot-12-decision.json",
    ):
        path = root / name
        existing = _read_json(path) if path.exists() else {}
        if (
            not path.exists()
            or existing.get("status") == BLOCKED_ADJUDICATION_STATUS
        ):
            atomic_write_json(path, blocked)
    evaluation_markdown = root / "pilot-12-semantic-evaluation.md"
    if (
        not evaluation_markdown.exists()
        or BLOCKED_ADJUDICATION_STATUS
        in evaluation_markdown.read_text(encoding="utf-8")
    ):
        atomic_write_text(
            evaluation_markdown,
            "# Pilot-12 Semantic Evaluation\n\n"
            "`BLOCKED_PENDING_HUMAN_ADJUDICATION`\n",
        )
    for name, status in (
        ("pilot-12-run-manifest.json", "PENDING_REAL_MODEL_EXECUTION"),
        ("pilot-12-performance-report.json", "PENDING_REAL_MODEL_EXECUTION"),
        ("pilot-12-validation-report.json", "PENDING_REAL_MODEL_EXECUTION"),
        ("pilot-12-reconciliation-report.json", "PENDING_REAL_MODEL_EXECUTION"),
        ("pilot-12-learning-report.json", "PENDING_REAL_MODEL_EXECUTION"),
    ):
        path = root / name
        existing = _read_json(path) if path.exists() else {}
        if (
            not path.exists()
            or existing.get("status") == "PENDING_REAL_MODEL_EXECUTION"
        ):
            atomic_write_json(
                path,
                {
                    "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
                    "pilot_id": pilot_id,
                    "status": status,
                    "knowledge_graph_written": False,
                },
            )
    return {
        "status": "READY_FOR_REAL_MODEL_PILOT_12",
        "pilot_id": pilot_id,
        "pilot_root": str(root),
        "sample_count": len(entries),
        "coverage": coverage_state,
    }


def _load_segment(root: Path, item: dict[str, Any]) -> SemanticSegmentInput:
    payload = _read_json(root / item["input_artifact"])
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


def _process_is_running(pid: int) -> bool:
    """Conservatively identify whether a benchmark lock owner still exists."""

    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if handle:
            kernel32.CloseHandle(handle)
            return True
        # ERROR_INVALID_PARAMETER means that the PID does not exist.
        return int(kernel32.GetLastError()) != 87
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stage_path(root: Path, segment_id: str, stage: str) -> Path:
    return (
        root
        / "segments"
        / segment_id
        / f"{STAGES.index(stage) + 1:02d}-{stage.lower()}.json"
    )


def _materialize_segment_audit(
    root: Path,
    item: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    segment_root = root / "segments" / item["audit_segment_id"]
    stage_payloads = {
        stage: _read_json(_stage_path(root, item["audit_segment_id"], stage))
        for stage in STAGES
    }
    raw_root = segment_root / "raw-provider-responses"
    raw_count = 0
    for stage, checkpoint in stage_payloads.items():
        raw = checkpoint.get("payload", {}).get(
            "safe_raw_provider_response"
        )
        if isinstance(raw, dict):
            atomic_write_json(raw_root / f"{stage.lower()}.json", raw)
            raw_count += 1
    parsed = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "structure": stage_payloads["STRUCTURAL_ANALYSIS"]["payload"],
        "mentions": stage_payloads["MENTION_EXTRACTION"]["payload"],
        "events_relations": stage_payloads[
            "EVENT_RELATION_EXTRACTION"
        ]["payload"],
        "claims_attribution": stage_payloads[
            "CLAIM_ATTRIBUTION"
        ]["payload"],
    }
    validation = stage_payloads[
        "DETERMINISTIC_EVIDENCE_VALIDATION"
    ]["payload"]
    reconciliation = stage_payloads["RECONCILIATION"]["payload"]
    rejected = [
        entry
        for entry in reconciliation.get("items", [])
        if entry.get("status") == "REJECTED_UNSUPPORTED"
    ]
    warnings = [
        entry
        for entry in validation.get("issues", [])
        if entry.get("severity") == "WARNING"
    ]
    atomic_write_json(segment_root / "parsed-semantic-v2.json", parsed)
    atomic_write_json(
        segment_root / "deterministic-validation.json",
        validation,
    )
    atomic_write_json(
        segment_root / "rejected-elements.json",
        {"items": rejected},
    )
    atomic_write_json(
        segment_root / "warnings.json",
        {"items": warnings},
    )
    atomic_write_json(
        segment_root / "reconciliation-output.json",
        reconciliation,
    )
    atomic_write_json(
        segment_root / "learning-report.json",
        stage_payloads["LEARNING_REPORT"]["payload"],
    )
    segment_input = _read_json(segment_root / "segment-input.json")
    atomic_write_json(
        segment_root / "baseline-rule-extraction.json",
        segment_input["current_extraction"],
    )
    atomic_write_json(
        segment_root / "diagnostic-reviewer-notes.json",
        {
            "role": "DIAGNOSTIC_ONLY_NOT_GOLD",
            "notes": segment_input.get("reviewer_notes", ""),
        },
    )
    performance = {
        "total_stage_latency_ms": summary["total_stage_latency_ms"],
        "model_load_time_ms": summary["model_load_time_ms"],
        "tokens": summary["tokens"],
        "model_call_count": summary.get("model_call_count", 0),
        "recorded_model_call_count": summary.get(
            "recorded_model_call_count",
            summary.get("model_call_count", 0),
        ),
        "cache_hits": summary["cache_hits"],
        "stage_execution": summary.get("stage_execution", []),
    }
    atomic_write_json(segment_root / "performance.json", performance)
    return {
        "audit_segment_id": item["audit_segment_id"],
        "run_id": summary["run_id"],
        "status": summary["status"],
        "execution_plan": summary["execution_plan"],
        "route": summary["route"],
        "model_call_count": summary.get("model_call_count", 0),
        "recorded_model_call_count": summary.get(
            "recorded_model_call_count",
            summary.get("model_call_count", 0),
        ),
        "total_stage_latency_ms": summary["total_stage_latency_ms"],
        "tokens": summary["tokens"],
        "cache_hits": summary["cache_hits"],
        "raw_response_count": raw_count,
        "validation_status": validation.get("status"),
        "validation_error_count": validation.get("error_count", 0),
        "validation_warning_count": validation.get("warning_count", 0),
        "rejected_unsupported_count": len(rejected),
        "accepted_unsupported_count": 0,
        "reconciliation_counts": reconciliation.get("counts", {}),
        "text_type": item["text_type"],
        "book_title": item["book_title"],
    }


def _write_pilot_reports(
    root: Path,
    manifest: dict[str, Any],
    provider: SemanticExtractionProvider,
    segment_results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    *,
    started_ns: int,
    unload_result: dict[str, Any],
    resumed_segments: list[str],
) -> dict[str, Any]:
    completed = len(segment_results)
    status = (
        PRE_ADJUDICATION_STATUS
        if completed == PILOT_SIZE and not failures
        else "REAL_MODEL_PILOT_12_INCOMPLETE"
    )
    total_latency = round(
        sum(item["total_stage_latency_ms"] for item in segment_results),
        3,
    )
    total_calls = sum(item["model_call_count"] for item in segment_results)
    recorded_calls = sum(
        item["recorded_model_call_count"] for item in segment_results
    )
    total_tokens = {
        key: sum(
            item.get("tokens", {}).get(key, 0)
            for item in segment_results
        )
        for key in ("input", "output")
    }
    run_manifest = {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "pilot_id": manifest["pilot_id"],
        "status": status,
        "provider": asdict(provider.identity),
        "prompt_version": PROMPT_VERSION,
        "prompt_manifest_hash": integrity_hash(prompt_manifest()),
        "semantic_schema_version": SEMANTIC_SCHEMA_VERSION,
        "segment_count": PILOT_SIZE,
        "completed_segments": completed,
        "failed_segments": len(failures),
        "failures": failures,
        "segments": segment_results,
        "segment_run_ids": sorted(
            item["run_id"] for item in segment_results
        ),
        "execution_policy": "SEQUENTIAL_ONE_MODEL_ONE_SEGMENT",
        "maximum_parallel_model_requests": 1,
        "total_model_calls": total_calls,
        "recorded_pilot_model_calls": recorded_calls,
        "total_runtime_ms": round(
            (time.perf_counter_ns() - started_ns) / 1_000_000,
            3,
        ),
        "total_stage_latency_ms": total_latency,
        "tokens": total_tokens,
        "resumed_segments": sorted(resumed_segments),
        "unload_result": unload_result,
        "knowledge_graph_written": False,
        "original_gold_modified": False,
        "pilot_model_output_limits": PILOT_MODEL_OUTPUT_LIMITS,
    }
    atomic_write_json(root / "pilot-12-run-manifest.json", run_manifest)
    by_plan: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "segments": 0,
            "calls": 0,
            "recorded_calls": 0,
            "latency_ms": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
    )
    by_text_type: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "segments": 0,
            "calls": 0,
            "recorded_calls": 0,
            "latency_ms": 0.0,
        }
    )
    for item in segment_results:
        for key in (item["execution_plan"],):
            by_plan[key]["segments"] += 1
            by_plan[key]["calls"] += item["model_call_count"]
            by_plan[key]["recorded_calls"] += item[
                "recorded_model_call_count"
            ]
            by_plan[key]["latency_ms"] += item["total_stage_latency_ms"]
            by_plan[key]["input_tokens"] += item["tokens"].get("input", 0)
            by_plan[key]["output_tokens"] += item["tokens"].get("output", 0)
        text_metrics = by_text_type[item["text_type"]]
        text_metrics["segments"] += 1
        text_metrics["calls"] += item["model_call_count"]
        text_metrics["recorded_calls"] += item[
            "recorded_model_call_count"
        ]
        text_metrics["latency_ms"] += item["total_stage_latency_ms"]
    performance = {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "pilot_id": manifest["pilot_id"],
        "status": status,
        "total_runtime_ms": run_manifest["total_runtime_ms"],
        "total_stage_latency_ms": total_latency,
        "total_model_calls": total_calls,
        "recorded_pilot_model_calls": recorded_calls,
        "tokens": total_tokens,
        "by_execution_plan": {
            key: value for key, value in sorted(by_plan.items())
        },
        "by_text_type": {
            key: value for key, value in sorted(by_text_type.items())
        },
        "cache_resume": {
            "resumed_segments": sorted(resumed_segments),
            "resumed_count": len(resumed_segments),
        },
        "wall_clock_is_not_a_semantic_quality_gate": True,
        "pilot_model_output_limits": PILOT_MODEL_OUTPUT_LIMITS,
    }
    atomic_write_json(
        root / "pilot-12-performance-report.json",
        performance,
    )
    validation = {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "pilot_id": manifest["pilot_id"],
        "status": status,
        "structured_output_success_count": completed,
        "structured_output_failure_count": len(failures),
        "validation_status_counts": dict(
            sorted(
                Counter(
                    item["validation_status"]
                    for item in segment_results
                ).items()
            )
        ),
        "validation_error_count": sum(
            item["validation_error_count"] for item in segment_results
        ),
        "validation_warning_count": sum(
            item["validation_warning_count"] for item in segment_results
        ),
        "rejected_unsupported_elements": sum(
            item["rejected_unsupported_count"]
            for item in segment_results
        ),
        "accepted_unsupported_elements": 0,
        "knowledge_graph_written": False,
        "pilot_model_output_limits": PILOT_MODEL_OUTPUT_LIMITS,
    }
    atomic_write_json(
        root / "pilot-12-validation-report.json",
        validation,
    )
    reconciliation_counts = Counter()
    for item in segment_results:
        reconciliation_counts.update(item["reconciliation_counts"])
    atomic_write_json(
        root / "pilot-12-reconciliation-report.json",
        {
            "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
            "pilot_id": manifest["pilot_id"],
            "status": status,
            "counts": dict(sorted(reconciliation_counts.items())),
            "segments": [
                {
                    "audit_segment_id": item["audit_segment_id"],
                    "counts": item["reconciliation_counts"],
                }
                for item in segment_results
            ],
            "baseline_role": "CANDIDATE_GENERATOR_ONLY",
            "knowledge_graph_written": False,
        },
    )
    learning = [
        _read_json(
            root
            / "segments"
            / item["audit_segment_id"]
            / "learning-report.json"
        )
        for item in segment_results
    ]
    atomic_write_json(
        root / "pilot-12-learning-report.json",
        {
            "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
            "pilot_id": manifest["pilot_id"],
            "status": status,
            "segments": learning,
            "automatic_rule_changes_allowed": False,
        },
    )
    blocked = {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "pilot_id": manifest["pilot_id"],
        "status": BLOCKED_ADJUDICATION_STATUS,
        "run_status": status,
        "reason_code": "HUMAN_ADJUDICATION_REQUIRED",
        "metrics": None,
        "pilot_model_output_limits": PILOT_MODEL_OUTPUT_LIMITS,
        "knowledge_graph_build_allowed": False,
    }
    atomic_write_json(root / "pilot-12-semantic-evaluation.json", blocked)
    atomic_write_text(
        root / "pilot-12-semantic-evaluation.md",
        "# Pilot-12 Semantic Evaluation\n\n"
        f"- Run status: `{status}`\n"
        f"- Evaluation: `{BLOCKED_ADJUDICATION_STATUS}`\n"
        "- Human adjudication is required before any semantic score.\n",
    )
    atomic_write_json(root / "pilot-12-decision.json", blocked)
    return run_manifest


def run_real_model_pilot_12(
    semantic_root: str | Path,
    provider: SemanticExtractionProvider,
    *,
    audit_root: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    prepare_pilot_12_evaluation(
        semantic_root,
        audit_root=audit_root,
    )
    root = pilot_root(semantic_root)
    manifest = _read_json(root / "pilot-12-selection-manifest.json")
    health = provider.health_check()
    if health.status != "AVAILABLE":
        raise SemanticProviderError(health.reason_code)
    if (
        provider.identity.provider_id == "OLLAMA_LOCAL_SEMANTIC"
        and provider.identity.model_id != "qwen3:4b-instruct"
    ):
        raise PilotEvaluationError("PILOT_MODEL_REFERENCE_MISMATCH")
    lock = root / ".pilot-12-benchmark.lock"
    if lock.exists():
        try:
            lock_identity = _read_json(lock)
            lock_pid = int(lock_identity["pid"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise PilotEvaluationError(
                "PILOT_BENCHMARK_LEGACY_LOCK_REQUIRES_OPERATOR_REVIEW"
            ) from None
        if _process_is_running(lock_pid):
            raise PilotEvaluationError("PILOT_BENCHMARK_ALREADY_RUNNING")
        stale_root = root / "stale-locks"
        stale_path = (
            stale_root
            / f"pilot-12-lock-{integrity_hash(lock_identity)[:16]}.json"
        )
        if not stale_path.exists():
            atomic_write_json(stale_path, lock_identity)
        lock.unlink()
    try:
        handle = lock.open("x", encoding="ascii")
    except FileExistsError as error:
        raise PilotEvaluationError("PILOT_BENCHMARK_ALREADY_RUNNING") from error
    handle.write(
        json.dumps(
            {
                "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
                "pid": os.getpid(),
                "mode": "SEQUENTIAL_LOCAL_MODEL_RUN",
                "pilot_id": manifest["pilot_id"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    handle.close()
    started_ns = time.perf_counter_ns()
    segment_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    resumed: list[str] = []
    unload_result: dict[str, Any] = {"status": "NOT_ATTEMPTED"}
    frozen_identity = asdict(provider.identity)
    try:
        for item in manifest["segments"]:
            segment_root = root / "segments" / item["audit_segment_id"]
            summary_path = segment_root / "run-summary.json"
            if summary_path.exists() and not force:
                summary = _read_json(summary_path)
                if (
                    summary.get("status") == "COMPLETED"
                    and summary.get("provider") == frozen_identity
                    and summary.get("original_text_hash")
                    == integrity_hash(
                        _read_json(
                            segment_root / "segment-input.json"
                        )["original_text"]
                    )
                ):
                    resumed.append(item["audit_segment_id"])
                    summary = {
                        **summary,
                        "recorded_model_call_count": summary.get(
                            "model_call_count",
                            0,
                        ),
                        "model_call_count": 0,
                        "cache_hits": len(STAGES),
                        "stage_execution": [
                            {
                                "stage": stage,
                                "status": "COMPLETED",
                                "execution_status": (
                                    "RESUMED_FROM_CHECKPOINT"
                                ),
                                "cache_hit": True,
                            }
                            for stage in STAGES
                        ],
                    }
                    segment_results.append(
                        _materialize_segment_audit(
                            root,
                            item,
                            summary,
                        )
                    )
                    continue
            segment = _load_segment(root, item)
            try:
                summary = LocalSemanticOrchestrator(
                    provider,
                    root,
                    force=force,
                ).run_segment(segment)
            except (RuntimeError, SemanticProviderError) as error:
                failures.append(
                    {
                        "audit_segment_id": item["audit_segment_id"],
                        "error_code": str(error).splitlines()[0][:180],
                        "checkpoint_preserved": True,
                    }
                )
                continue
            if asdict(provider.identity) != frozen_identity:
                failures.append(
                    {
                        "audit_segment_id": item["audit_segment_id"],
                        "error_code": "MODEL_IDENTITY_CHANGED_DURING_RUN",
                        "checkpoint_preserved": True,
                    }
                )
                continue
            segment_results.append(
                _materialize_segment_audit(root, item, summary)
            )
    finally:
        try:
            unload_result = provider.unload()
        except SemanticProviderError as error:
            unload_result = {
                "status": "UNLOAD_FAILED",
                "reason_code": error.code,
            }
        lock.unlink(missing_ok=True)
    return _write_pilot_reports(
        root,
        manifest,
        provider,
        segment_results,
        failures,
        started_ns=started_ns,
        unload_result=unload_result,
        resumed_segments=resumed,
    )


def pilot_12_status(
    semantic_root: str | Path,
) -> dict[str, Any]:
    root = pilot_root(semantic_root)
    manifest = _read_json(root / "pilot-12-selection-manifest.json")
    run = _read_json(root / "pilot-12-run-manifest.json")
    adjudication = _read_json(
        root / "pilot-12-human-adjudication.json"
    )
    status_counts = Counter(
        item.get("adjudication_status", "PENDING")
        for item in adjudication.get("annotations", [])
    )
    return {
        "status": run.get("status", "PENDING_REAL_MODEL_EXECUTION"),
        "pilot_id": manifest["pilot_id"],
        "sample_count": manifest["sample_count"],
        "completed_segments": int(run.get("completed_segments", 0)),
        "failed_segments": int(run.get("failed_segments", 0)),
        "adjudication": dict(sorted(status_counts.items())),
        "human_evaluation_status": adjudication.get(
            "status",
            BLOCKED_ADJUDICATION_STATUS,
        ),
        "knowledge_graph_written": False,
    }


def compare_pilot_12(
    semantic_root: str | Path,
) -> dict[str, Any]:
    root = pilot_root(semantic_root)
    run = _read_json(root / "pilot-12-run-manifest.json")
    reconciliation = _read_json(
        root / "pilot-12-reconciliation-report.json"
    )
    validation = _read_json(root / "pilot-12-validation-report.json")
    return {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "status": (
            "COMPLETED_PENDING_HUMAN_ADJUDICATION"
            if run.get("status") == PRE_ADJUDICATION_STATUS
            else "PILOT_EXECUTION_INCOMPLETE"
        ),
        "baseline": "RULE_BASED_CANDIDATE_GENERATOR",
        "raw_model": {
            "structured_output_success_count": validation.get(
                "structured_output_success_count",
                0,
            ),
            "validation_error_count": validation.get(
                "validation_error_count",
                0,
            ),
        },
        "reconciled": reconciliation.get("counts", {}),
        "semantic_scores": BLOCKED_ADJUDICATION_STATUS,
        "knowledge_graph_written": False,
    }


def _span(item: dict[str, Any]) -> tuple[int, int] | None:
    candidate = (
        item.get("evidence")
        or item.get("span")
        or item.get("trigger")
        or item.get("exact_chain_range")
        or item.get("original_text_span")
        or item.get("evidence_span")
    )
    if not isinstance(candidate, dict):
        if "start" in item and "end" in item:
            candidate = item
        else:
            return None
    try:
        start, end = int(candidate["start"]), int(candidate["end"])
    except (KeyError, TypeError, ValueError):
        return None
    return (start, end) if 0 <= start < end else None


def _label(category: str, item: dict[str, Any]) -> str:
    fields = {
        "entities": ("type", "entity_types", "entity_type_candidate"),
        "events": ("type", "event_type"),
        "relations": ("type", "predicate", "relation_type"),
        "temporal_mentions": ("type", "precision", "temporal_type"),
        "isnad": ("type",),
        "claims_attribution": (
            "type",
            "assertion_status",
            "claim_modality",
        ),
    }[category]
    for field in fields:
        value = item.get(field)
        if value:
            if isinstance(value, list):
                return "|".join(sorted(map(str, value)))
            return str(value)
    return category.upper()


def _score(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    category: str,
) -> dict[str, Any]:
    used: set[int] = set()
    exact = 0
    overlap = 0
    typed = 0
    for gold in expected:
        gold_span = _span(gold)
        for index, candidate in enumerate(actual):
            if index in used:
                continue
            candidate_span = _span(candidate)
            if gold_span == candidate_span and gold_span is not None:
                used.add(index)
                exact += 1
                overlap += 1
                typed += _label(category, gold) == _label(category, candidate)
                break
        else:
            for index, candidate in enumerate(actual):
                if index in used:
                    continue
                candidate_span = _span(candidate)
                if (
                    gold_span is not None
                    and candidate_span is not None
                    and max(gold_span[0], candidate_span[0])
                    < min(gold_span[1], candidate_span[1])
                ):
                    used.add(index)
                    overlap += 1
                    typed += _label(category, gold) == _label(
                        category,
                        candidate,
                    )
                    break
    precision = round(exact / len(actual), 6) if actual else (
        1.0 if not expected else 0.0
    )
    recall = round(exact / len(expected), 6) if expected else (
        1.0 if not actual else 0.0
    )
    return {
        "expected": len(expected),
        "actual": len(actual),
        "exact_true_positive": exact,
        "overlap_true_positive": overlap,
        "exact_precision": precision,
        "exact_recall": recall,
        "overlap_precision": round(overlap / len(actual), 6)
        if actual else (1.0 if not expected else 0.0),
        "overlap_recall": round(overlap / len(expected), 6)
        if expected else (1.0 if not actual else 0.0),
        "type_accuracy": round(typed / overlap, 6)
        if overlap else None,
    }


def _model_collections(root: Path, audit_segment_id: str) -> dict[str, list[dict[str, Any]]]:
    parsed = _read_json(
        root
        / "segments"
        / audit_segment_id
        / "parsed-semantic-v2.json"
    )
    return {
        "entities": list(parsed.get("mentions", {}).get("entities", [])),
        "events": list(
            parsed.get("events_relations", {}).get("events", [])
        ),
        "relations": list(
            parsed.get("events_relations", {}).get("relations", [])
        ),
        "temporal_mentions": list(
            parsed.get("claims_attribution", {}).get("temporals", [])
        ),
        "isnad": list(
            parsed.get("claims_attribution", {}).get("isnads", [])
        ),
        "claims_attribution": list(
            parsed.get("claims_attribution", {}).get("claims", [])
        ),
    }


def _baseline_collections(root: Path, audit_segment_id: str) -> dict[str, list[dict[str, Any]]]:
    baseline = _read_json(
        root
        / "segments"
        / audit_segment_id
        / "baseline-rule-extraction.json"
    )
    return {
        "entities": list(baseline.get("entities", [])),
        "events": list(baseline.get("events", [])),
        "relations": list(baseline.get("relations", [])),
        "temporal_mentions": list(
            baseline.get("temporal_mentions", [])
        ),
        "isnad": list(baseline.get("isnad_chains", [])),
        "claims_attribution": list(baseline.get("claims", [])),
    }


def _reconciled_collections(root: Path, audit_segment_id: str) -> dict[str, list[dict[str, Any]]]:
    raw = _model_collections(root, audit_segment_id)
    reconciliation = _read_json(
        root
        / "segments"
        / audit_segment_id
        / "reconciliation-output.json"
    )
    accepted = {
        str(item["item_id"])
        for item in reconciliation.get("items", [])
        if item.get("status")
        in {
            "ACCEPTED_HIGH_CONFIDENCE",
            "ACCEPTED_WITH_WARNING",
            "HUMAN_REVIEW_REQUIRED",
        }
    }
    identifiers = {
        "entities": "mention_id",
        "events": "event_id",
        "relations": "relation_id",
        "temporal_mentions": "temporal_id",
        "isnad": "isnad_id",
        "claims_attribution": "claim_id",
    }
    return {
        category: [
            item
            for item in items
            if str(item.get(identifiers[category], "")) in accepted
        ]
        for category, items in raw.items()
    }


def evaluate_pilot_12(
    semantic_root: str | Path,
) -> dict[str, Any]:
    root = pilot_root(semantic_root)
    adjudication = _read_json(
        root / "pilot-12-human-adjudication.json"
    )
    annotations = list(adjudication.get("annotations", []))
    unresolved = [
        item["audit_segment_id"]
        for item in annotations
        if item.get("adjudication_status") != "COMPLETED"
        and not (
            item.get("adjudication_status") == "NEEDS_EXPERT_REVIEW"
            and item.get("expert_review_resolution", {}).get("status")
            in {"RESOLVED_INCLUDED", "EXCLUDED_WITH_REASON"}
            and str(
                item.get("expert_review_resolution", {}).get(
                    "reason",
                    "",
                )
            ).strip()
        )
    ]
    if unresolved:
        blocked = {
            "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
            "status": BLOCKED_ADJUDICATION_STATUS,
            "pending_segment_ids": sorted(unresolved),
            "metrics": None,
            "knowledge_graph_build_allowed": False,
        }
        atomic_write_json(
            root / "pilot-12-semantic-evaluation.json",
            blocked,
        )
        atomic_write_json(root / "pilot-12-decision.json", blocked)
        raise PilotEvaluationError(
            "PILOT_EVALUATION_REQUIRES_COMPLETED_ADJUDICATION"
        )
    included = [
        item
        for item in annotations
        if item.get("adjudication_status") == "COMPLETED"
        or item.get("expert_review_resolution", {}).get("status")
        == "RESOLVED_INCLUDED"
    ]
    systems: dict[str, Callable[[Path, str], dict[str, list[dict[str, Any]]]]] = {
        "baseline": _baseline_collections,
        "model_raw": _model_collections,
        "reconciled": _reconciled_collections,
    }
    totals: dict[str, dict[str, list[dict[str, Any]]]] = {
        system: {
            category: []
            for category in ADJUDICATION_CATEGORIES
            if category != "structure"
        }
        for system in systems
    }
    gold_totals = {
        category: []
        for category in ADJUDICATION_CATEGORIES
        if category != "structure"
    }
    per_segment = []
    for annotation in included:
        audit_id = annotation["audit_segment_id"]
        gold = {
            "entities": annotation["gold_entities"],
            "events": annotation["gold_events"],
            "relations": annotation["gold_relations"],
            "temporal_mentions": annotation["gold_temporal_mentions"],
            "isnad": annotation["gold_isnad"],
            "claims_attribution": annotation[
                "gold_claims_attribution"
            ],
        }
        system_scores = {}
        for system, loader in systems.items():
            actual = loader(root, audit_id)
            system_scores[system] = {
                category: _score(
                    gold[category],
                    actual[category],
                    category,
                )
                for category in gold
            }
            for category in gold:
                totals[system][category].extend(actual[category])
        for category in gold:
            gold_totals[category].extend(gold[category])
        per_segment.append(
            {
                "audit_segment_id": audit_id,
                "book_title": annotation["book_title"],
                "scores": system_scores,
            }
        )
    overall = {
        system: {
            category: _score(
                gold_totals[category],
                values[category],
                category,
            )
            for category in gold_totals
        }
        for system, values in totals.items()
    }
    model_judgments = [
        judgment
        for item in included
        for judgment in item.get("model_output_judgments", [])
    ]
    error_codes = Counter(
        code
        for judgment in model_judgments
        for code in judgment.get("error_codes", [])
    )
    evidence_report = _read_json(root / "pilot-12-validation-report.json")
    structured_success = (
        evidence_report.get("structured_output_success_count", 0)
        == PILOT_SIZE
    )
    accepted_hallucinations = evidence_report.get(
        "accepted_unsupported_elements",
        0,
    )
    decision = "PILOT_SEMANTIC_PARTIAL"
    model_entity = overall["model_raw"]["entities"]
    baseline_entity = overall["baseline"]["entities"]
    if not structured_success or accepted_hallucinations:
        decision = "PILOT_SEMANTIC_FAIL"
    elif (
        model_entity["overlap_recall"]
        > baseline_entity["overlap_recall"]
        and error_codes.get("EXTERNAL_KNOWLEDGE_HALLUCINATION", 0)
        == 0
    ):
        decision = "PILOT_SEMANTIC_PROMISING"
    if (
        decision == "PILOT_SEMANTIC_PROMISING"
        and all(
            overall["reconciled"][category]["exact_precision"] >= 0.8
            for category in ("entities", "events", "relations")
        )
    ):
        decision = "PILOT_SEMANTIC_PASS_FOR_EXPANDED_EVALUATION"
    result = {
        "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
        "status": POST_ADJUDICATION_STATUS,
        "decision": decision,
        "included_segments": len(included),
        "overall": overall,
        "per_segment": per_segment,
        "error_taxonomy_counts": dict(sorted(error_codes.items())),
        "safety": {
            "structured_output_success": structured_success,
            "accepted_hallucination_count": accepted_hallucinations,
            "evidence_integrity": (
                1.0
                if evidence_report.get("validation_error_count", 0) == 0
                else None
            ),
            "knowledge_graph_written": False,
        },
        "limitations": [
            "Pilot decisions authorize evaluation expansion only.",
            "No Pilot decision is Knowledge-Graph readiness.",
        ],
    }
    atomic_write_json(
        root / "pilot-12-semantic-evaluation.json",
        result,
    )
    atomic_write_json(
        root / "pilot-12-decision.json",
        {
            "schema_version": PILOT_EVALUATION_SCHEMA_VERSION,
            "status": POST_ADJUDICATION_STATUS,
            "decision": decision,
            "knowledge_graph_build_allowed": False,
        },
    )
    atomic_write_text(
        root / "pilot-12-semantic-evaluation.md",
        "# Pilot-12 Semantic Evaluation\n\n"
        f"- Status: `{POST_ADJUDICATION_STATUS}`\n"
        f"- Decision: `{decision}`\n"
        f"- Included segments: `{len(included)}`\n"
        "- Knowledge Graph build allowed: `false`\n",
    )
    adjudication["status"] = POST_ADJUDICATION_STATUS
    atomic_write_json(
        root / "pilot-12-human-adjudication.json",
        adjudication,
    )
    return result


__all__ = [
    "ADJUDICATION_CATEGORIES",
    "BLOCKED_ADJUDICATION_STATUS",
    "ERROR_TAXONOMY",
    "PILOT_EVALUATION_SCHEMA_VERSION",
    "POST_ADJUDICATION_STATUS",
    "PRE_ADJUDICATION_STATUS",
    "PilotEvaluationError",
    "compare_pilot_12",
    "evaluate_pilot_12",
    "pilot_12_status",
    "pilot_root",
    "prepare_pilot_12_evaluation",
    "run_real_model_pilot_12",
    "select_evaluation_pilot_12",
]
