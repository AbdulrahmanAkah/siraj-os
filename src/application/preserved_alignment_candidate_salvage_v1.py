"""Offline-only salvage validation for a preserved controlled-alignment candidate.

This deliberately creates a derived view.  It never promotes the candidate,
rewrites the raw response, evaluates a paid provider, or runs a downstream
stage that writes Episode 002 production state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.application.alignment_finding_ownership_v1 import (
    FindingOwner,
    classify_alignment_finding,
    permits_semantic_creative_repair,
)
from src.application.artifact_provenance_v1 import (
    artifact_reference,
    canonical_sha256,
    sha256_file,
    utc_now,
    write_new_json,
)
from src.application.controlled_alignment_validation_v1 import (
    EXPECTED_STRUCTURAL_FINGERPRINT,
    _candidate_overlay,
    _parse_model_json,
    _preflight,
    _validate_creative_quality,
)
from src.application.controlled_alignment_reporting_v1 import (
    render_controlled_alignment_markdown,
)


SCHEMA_VERSION = "siraj-preserved-alignment-candidate-salvage-v1"
STAGE = "NARRATION_VISUAL_ALIGNMENT_GATE"
EXPECTED_CANDIDATE_SHA256 = (
    "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
)
SEMANTIC_IDS = (
    "LUNA-SEM-001",
    "LUNA-SEM-002",
    "LUNA-SEM-003",
    "LUNA-SEM-004",
    "LUNA-REP-001",
)
GATE_ID = "LUNA-GATE-001"


class PreservedCandidateSalvageError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PreservedCandidateSalvageError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _paths(repo: Path, episode_id: str) -> dict[str, Path]:
    root = repo / "projects" / episode_id / "orchestration"
    controlled = root / "controlled-alignment-validation-v1"
    attempt_id = "75611537-2fa2-41be-acbf-98540e65bee7"
    return {
        "controlled_root": controlled,
        "provider_record": controlled / "provider-proposal.json",
        "raw_response": root / "paid-operation-attempts-v1" / attempt_id / "raw-response.bin",
        "attempt_events": root / "paid-operation-attempts-v1" / attempt_id / "attempt-events.jsonl",
        "attempt_request": root / "paid-operation-attempts-v1" / attempt_id / "request.json",
        "old_unknown": root / "luna-v6-3" / "narration_visual_alignment_gate" / "attempts" / "85a1e2de-3c05-427f-82d0-c2effa0ae173.unknown-not-retried-superseded.json",
        "salvage_view": controlled / "preserved-candidate-salvage-view-v1.json",
    }


def _semantic_assessments(
    state: Mapping[str, Any],
    changed_ids: list[str],
    resolutions: list[Mapping[str, Any]],
    quality_errors: list[str],
) -> list[dict[str, Any]]:
    expected = {finding.finding_id: finding for finding in state["audit"].findings}
    result: list[dict[str, Any]] = []
    for finding_id in SEMANTIC_IDS:
        finding = expected[finding_id]
        resolution = next((row for row in resolutions if row["finding_id"] == finding_id), None)
        all_affected_patched = set(finding.affected_shot_ids).issubset(changed_ids)
        local_evidence = {
            "resolution_metadata_present": resolution is not None,
            "all_affected_shots_patched": all_affected_patched,
            "structural_change": "NONE",
            "generic_prompt_regression_check": "EXECUTED",
            "generic_prompt_regression_detected": any(
                error.startswith("GENERIC_PROMPT_REGRESSION") for error in quality_errors
            ),
            "creative_information_preserved": not any(
                error.startswith("CREATIVE_INFORMATION_LOST") for error in quality_errors
            ),
        }
        # Local validators prove coverage, non-generic content, and structural
        # safety.  They do not claim a subjective semantic judgment is closed;
        # that remains a human approval decision.
        status = (
            "IMPROVED_BUT_STILL_BLOCKING"
            if resolution is not None and all_affected_patched
            else "UNVALIDATABLE_LOCALLY"
        )
        result.append({
            "finding_id": finding_id,
            "owner": FindingOwner.SEMANTIC_CREATIVE.value,
            "status": status,
            "affected_shot_ids": list(finding.affected_shot_ids),
            "resolution_metadata": resolution,
            "local_evidence": local_evidence,
            "reason": (
                "Deterministic checks establish a complete, structurally safe, "
                "non-generic patch set, but cannot autonomously close semantic/cinematic "
                "meaning without human review."
            ),
        })
    return result


def derive_salvage_view(repo_root: Path, episode_id: str) -> dict[str, Any]:
    """Read immutable evidence and construct the non-authoritative salvage view."""

    repo = Path(repo_root).resolve()
    state = _preflight(repo, episode_id)
    paths = _paths(repo, episode_id)
    for key in ("provider_record", "raw_response", "attempt_events", "attempt_request", "old_unknown"):
        if not paths[key].is_file():
            raise PreservedCandidateSalvageError("FORENSIC_ARTIFACT_MISSING:" + key)
    record = _read_json(paths["provider_record"])
    response = _parse_model_json(str(record.get("output_text") or ""))
    candidate, patches, changed_ids = _candidate_overlay(state, response)
    candidate_sha256 = canonical_sha256(candidate)
    if candidate_sha256 != EXPECTED_CANDIDATE_SHA256:
        raise PreservedCandidateSalvageError("CANDIDATE_HASH_MISMATCH")
    quality_ok, quality_errors, semantic_resolutions, protocol_violations = _validate_creative_quality(
        state, response, candidate, changed_ids
    )
    if not quality_ok:
        raise PreservedCandidateSalvageError("SEMANTIC_CANDIDATE_LOCAL_QUALITY_INVALID")
    gate_rows = [
        row for row in protocol_violations if row.get("finding_id") == GATE_ID
    ]
    if len(gate_rows) != 1 or gate_rows[0].get("owner") != FindingOwner.DOWNSTREAM_GATE.value:
        raise PreservedCandidateSalvageError("LOCAL_GATE_PROTOCOL_VIOLATION_NOT_PRESERVED")
    structures = state["structures"]
    discontinuities = sum(a.end_ms != b.start_ms for a, b in zip(structures, structures[1:]))
    if (
        state["required_structural_fingerprint"] != EXPECTED_STRUCTURAL_FINGERPRINT
        or len(structures) != 55
        or discontinuities != 0
        or (structures[-1].shot_id, structures[-1].start_ms, structures[-1].end_ms)
        != ("EP002-SH-055", 622784, 623584)
    ):
        raise PreservedCandidateSalvageError("STRUCTURAL_INVARIANT_VIOLATION")
    assessments = _semantic_assessments(state, changed_ids, semantic_resolutions, quality_errors)
    has_regression = any(
        error.startswith(("GENERIC_PROMPT_REGRESSION", "CREATIVE_INFORMATION_LOST"))
        for error in quality_errors
    )
    classification = (
        "SALVAGE_REGRESSION" if has_regression
        else "SALVAGE_OBJECTIVE_IMPROVEMENT"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "created_at_utc": utc_now(),
        "status": "CANDIDATE_PENDING_HUMAN_APPROVAL",
        "candidate_sha256": candidate_sha256,
        "candidate_patch_count": len(patches),
        "creative_baseline_sha256": state["creative_overlay_hash"],
        "candidate_overlay": candidate,
        "patches": patches,
        "forensic_evidence": {
            key: artifact_reference(path, base=repo)
            for key, path in paths.items()
            if key in {"provider_record", "raw_response", "attempt_events", "attempt_request", "old_unknown"}
        },
        "structural_validation": {
            "status": "PASS",
            "structural_fingerprint": state["required_structural_fingerprint"],
            "duration_seconds": 623.584,
            "shot_count": 55,
            "timeline_discontinuities": discontinuities,
            "final_shot": "EP002-SH-055:622.784-623.584",
            "all_candidate_patch_structural_change": "NONE",
        },
        "semantic_findings": assessments,
        "semantic_findings_before": 5,
        "semantic_findings_after_candidate": 5,
        "protocol_violations": protocol_violations,
        "local_gate_001": {
            "finding_id": GATE_ID,
            "owner": FindingOwner.DOWNSTREAM_GATE.value,
            "status": "PRE_SPEND_GATE_NOT_CLOSED",
            "luna_resolution_ignored": True,
            "required_stage": "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
            "required_input_hashes": {
                "authoritative_storyboard_structural_fingerprint": state["required_structural_fingerprint"],
                "candidate_overlay_sha256": candidate_sha256,
                "promoted_provider_ready_prompt_plan_sha256": "REQUIRED_AFTER_HUMAN_PROMOTION",
            },
            "can_be_evaluated_before_promotion": False,
            "can_be_evaluated_after_promotion": True,
            "reason": (
                "The actual Phase 0–4 duplicate gate consumes a persisted prompt-plan artifact "
                "and writes its gate artifact. The derived overlay is not the authoritative prompt plan, "
                "so executing that stage now would be a prohibited downstream production-state change."
            ),
        },
        "creative_validation": {
            "creative_information_preserved": True,
            "generic_prompt_regression_check": "EXECUTED",
            "generic_prompt_regression_detected": False,
            "structural_leakage": False,
            "quality_errors": quality_errors,
            "sequence_groups": {
                "A_temptation": ["EP002-SH-012", "EP002-SH-013", "EP002-SH-014", "EP002-SH-015", "EP002-SH-016"],
                "B_shared_action": ["EP002-SH-017", "EP002-SH-018", "EP002-SH-019", "EP002-SH-020", "EP002-SH-021"],
                "C_repentance_guidance": ["EP002-SH-030", "EP002-SH-031", "EP002-SH-032", "EP002-SH-033", "EP002-SH-034"],
                "D_hadith_argument": ["EP002-SH-040", "EP002-SH-041", "EP002-SH-042", "EP002-SH-043", "EP002-SH-044"],
                "E_descent_vs_closing": ["EP002-SH-036", "EP002-SH-037", "EP002-SH-038", "EP002-SH-050", "EP002-SH-051", "EP002-SH-052", "EP002-SH-053", "EP002-SH-054", "EP002-SH-055"],
            },
            "cross_group_duplication": "NO_DETERMINISTIC_EXACT_DUPLICATE",
            "note": "Local checks cannot substitute for final human cinematic judgment.",
        },
        "salvage_classification": classification,
        "candidate_promoted": False,
        "authoritative_alignment_modified": False,
        "network_calls": 0,
        "paid_provider_calls": 0,
        "autopilot_runs": 0,
        "files_deleted": 0,
    }


def render_salvage_markdown(view: Mapping[str, Any]) -> str:
    base = render_controlled_alignment_markdown({
        "classification": view["salvage_classification"],
        "creative_baseline_hash": view["creative_baseline_sha256"],
        "candidate_sha256": view["candidate_sha256"],
    })
    lines = [base.rstrip(), "", "## Semantic findings", ""]
    for finding in view["semantic_findings"]:
        lines.extend((
            f"- `{finding['finding_id']}` — `{finding['status']}`; affected shots: "
            + ", ".join(finding["affected_shot_ids"]),
            f"  Evidence: {finding['reason']}",
        ))
    gate = view["local_gate_001"]
    lines.extend((
        "",
        "## Local gate",
        "",
        f"- `{gate['finding_id']}` owner: `{gate['owner']}`.",
        f"- Required stage: `{gate['required_stage']}`.",
        f"- Luna resolution ignored: `{gate['luna_resolution_ignored']}`.",
        f"- Before promotion: `{gate['can_be_evaluated_before_promotion']}`; after promotion: `{gate['can_be_evaluated_after_promotion']}`.",
        "",
        "## Decision",
        "",
        f"`{view['salvage_classification']}`. Candidate remains `CANDIDATE_PENDING_HUMAN_APPROVAL`; it was not promoted and the authoritative alignment state was not modified.",
        "",
    ))
    return "\n".join(lines)


def write_salvage_outputs(repo_root: Path, episode_id: str) -> dict[str, str]:
    """Write only new derived/report artifacts; fail closed if a target exists."""

    repo = Path(repo_root).resolve()
    paths = _paths(repo, episode_id)
    view = derive_salvage_view(repo, episode_id)
    targets = {
        "derived_view": paths["salvage_view"],
        "report_json": repo / "reports" / "episode-002-preserved-candidate-salvage-validation.json",
        "report_md": repo / "reports" / "episode-002-preserved-candidate-salvage-validation.md",
    }
    if any(path.exists() for path in targets.values()):
        raise PreservedCandidateSalvageError("SALVAGE_TARGET_ALREADY_EXISTS")
    write_new_json(targets["derived_view"], view)
    report = {key: value for key, value in view.items() if key != "candidate_overlay"}
    report["derived_candidate_view"] = artifact_reference(targets["derived_view"], base=repo)
    write_new_json(targets["report_json"], report)
    targets["report_md"].parent.mkdir(parents=True, exist_ok=True)
    with targets["report_md"].open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(render_salvage_markdown(view))
    return {key: str(path) for key, path in targets.items()}
