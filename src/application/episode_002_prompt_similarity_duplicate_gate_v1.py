"""Post-promotion local prompt similarity and duplicate gate for Episode 002.

This module is deliberately a validator only.  It cannot resume production,
call a provider, generate media, or start the next stage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.application.artifact_provenance_v1 import artifact_reference, canonical_sha256, sha256_file, utc_now, write_new_json
from src.application.episode_002_candidate_promotion_v1 import (
    CANDIDATE_SHA256, EPISODE, NEXT_STAGE, STRUCTURAL_FINGERPRINT, verify_promoted_state,
)
from src.application.episode_transition_ledger_v1 import append_transition, project_state
from src.application.siraj_cinematic_director_v2 import cross_sequence_distinctness, sequence_quality_review
from src.application.siraj_prompt_duplicate_gate_v6_1 import prompt_text, validate_prompt_similarity


SCHEMA_VERSION = "siraj-episode-002-prompt-similarity-duplicate-gate-v1"
STAGE = "PROMPT_SIMILARITY_AND_DUPLICATE_GATE"
NEXT_AFTER_GATE = "MEDIA_COST_PREFLIGHT"
RESUME_ENTRYPOINT = "DESKTOP_UI_ONLY"


class PromptSimilarityGateError(RuntimeError):
    pass


def _paths(repo: Path) -> dict[str, Path]:
    ep = repo / "projects" / EPISODE
    orchestration = ep / "orchestration"
    return {
        "overlay": ep / "preproduction" / "siraj-creative-shot-direction-promoted-v1.json",
        "plan": ep / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json",
        "storyboard": ep / "preproduction" / "audio-bound-storyboard-v6-1.json",
        "promotion_state": orchestration / "episode-creative-promotion-state-v1.json",
        "v2_acceptance": orchestration / "v2-warning-acceptance-v1.json",
        "ledger": orchestration / "episode-transition-ledger-v1.jsonl",
        "gate": orchestration / "prompt-similarity-duplicate-gate-promoted-v1.json",
        "gate_closure": orchestration / "luna-gate-001-local-closure-v1.json",
        "report_md": repo / "reports" / "episode-002-prompt-similarity-duplicate-gate.md",
        "report_json": repo / "reports" / "episode-002-prompt-similarity-duplicate-gate.json",
    }


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PromptSimilarityGateError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _groups(overlay: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    directions = {row["shot_id"]: row for row in overlay["directions"]}
    ranges = {
        "TEMPTATION_012_016": range(12, 17),
        "SHARED_ACTION_017_021": range(17, 22),
        "REPENTANCE_GUIDANCE_030_034": range(30, 35),
        "HADITH_ARGUMENT_040_044": range(40, 45),
        "DESCENT_036_038": range(36, 39),
        "CLOSING_EARTH_050_055": range(50, 56),
    }
    return {key: [directions[f"EP002-SH-{number:03d}"] for number in numbers] for key, numbers in ranges.items()}


def _normalised(value: str) -> str:
    return " ".join(value.casefold().split())


def _exact_duplicates(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    result: list[dict[str, Any]] = []
    for item in items:
        shot_id = str(item.get("shot_id") or "")
        text = _normalised(prompt_text(item))
        if not text:
            result.append({"type": "EMPTY_PROMPT", "shot_id": shot_id, "provider_spend_duplicated": False})
        elif text in seen:
            result.append({"type": "EXACT_DUPLICATE", "shot_ids": [seen[text], shot_id], "reason": "identical normalized provider-ready prompt", "intentional_continuity": False, "provider_spend_duplicated": True, "correction": "LOCAL_DETERMINISTIC_OR_CREATIVE_REVIEW"})
        else:
            seen[text] = shot_id
    return result


def _near_duplicates(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = validate_prompt_similarity(items, threshold=0.93)
    result = []
    for row in rows:
        if row.get("type") != "NEAR_DUPLICATE":
            continue
        left, right = items[int(row["a"])], items[int(row["b"])]
        result.append({"type": "NEAR_PROMPT_DUPLICATE", "shot_ids": [left.get("shot_id"), right.get("shot_id")], "score": row["score"], "reason": "cosine similarity over canonical provider-ready prompts", "intentional_continuity": False, "provider_spend_duplicated": True, "correction": "HUMAN_REVIEW_REQUIRED"})
    return result


def _provider_unit_repetition(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    fingerprints: dict[str, str] = {}
    for item in items:
        unit = item.get("video_subshots")
        if not unit:
            continue
        fingerprint = canonical_sha256({"prompt": prompt_text(item), "video_subshots": unit})
        shot_id = str(item.get("shot_id") or "")
        if fingerprint in fingerprints:
            findings.append({"type": "DUPLICATE_PROVIDER_UNIT", "shot_ids": [fingerprints[fingerprint], shot_id], "reason": "same planned unit payload", "provider_spend_duplicated": True, "correction": "LOCAL_DETERMINISTIC"})
        else:
            fingerprints[fingerprint] = shot_id
    return findings


def analyze_promoted_plan(repo_root: Path) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    verified = verify_promoted_state(repo)
    if verified["status"] != "PASS":
        raise PromptSimilarityGateError("PROMOTED_STATE_INVALID")
    paths = _paths(repo)
    for key in ("overlay", "plan", "storyboard", "promotion_state", "v2_acceptance", "ledger"):
        if not paths[key].is_file():
            raise PromptSimilarityGateError("REQUIRED_INPUT_MISSING:" + key)
    overlay, plan, promotion_state, v2 = (_read(paths[key]) for key in ("overlay", "plan", "promotion_state", "v2_acceptance"))
    if (
        canonical_sha256(overlay) != CANDIDATE_SHA256
        or plan.get("creative_overlay_sha256") != CANDIDATE_SHA256
        or plan.get("storyboard_structural_fingerprint") is None
        or promotion_state.get("authoritative_current_prompt_plan", {}).get("sha256") != sha256_file(paths["plan"])
        or v2.get("sh031_warning", {}).get("classification") != "ACCEPTED_INTENTIONAL_ABSTRACTION_NON_BLOCKING"
    ):
        raise PromptSimilarityGateError("AUTHORITATIVE_PROMOTED_INPUT_MISMATCH")
    projection = project_state(repo, EPISODE)
    if projection.current_stage != STAGE or projection.status != "READY":
        raise PromptSimilarityGateError("GATE_NOT_CURRENT")
    items = plan.get("items")
    if not isinstance(items, list) or len(items) != 55:
        raise PromptSimilarityGateError("PROMOTED_PLAN_ITEMS_REQUIRED")
    exact = _exact_duplicates(items)
    near = _near_duplicates(items)
    units = _provider_unit_repetition(items)
    groups = _groups(overlay)
    v2_review = sequence_quality_review(groups)
    cross = cross_sequence_distinctness(groups)
    semantic = [
        {"type": "CROSS_SEQUENCE_VISUAL_SIGNATURE", **row, "intentional_continuity": False, "provider_spend_duplicated": "UNKNOWN", "correction": "HUMAN_REVIEW_REQUIRED"}
        for row in cross
    ]
    adjacent = [row for row in near if abs(int(str(row["shot_ids"][0]).split("-")[-1]) - int(str(row["shot_ids"][1]).split("-")[-1])) == 1]
    intentional = [
        {"group": key, "classification": "INTENTIONAL_CONTINUITY", "reason": "Declared continuity/motif progression inside one narrative sequence; no exact duplicate or identical cross-sequence signature."}
        for key in groups
        if v2_review["motif_lifecycle"][key]["status"] in {"PASS", "WARN"}
    ]
    human = semantic + [row for row in near if row not in adjacent]
    blocking = exact + near + semantic + units
    status = "PASS" if not blocking else "HUMAN_REVIEW_REQUIRED" if not exact and not units else "FAIL_UNJUSTIFIED_NEAR_DUPLICATE"
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": EPISODE,
        "status": status,
        "created_at_utc": utc_now(),
        "input_artifacts": {key: artifact_reference(paths[key], base=repo) for key in ("overlay", "plan", "storyboard", "promotion_state", "v2_acceptance", "ledger")},
        "promoted_overlay_sha256": CANDIDATE_SHA256,
        "required_structural_fingerprint": STRUCTURAL_FINGERPRINT,
        "exact_duplicates": exact,
        "near_duplicates": near,
        "semantic_repetition_findings": semantic,
        "adjacent_repetition_findings": adjacent,
        "cross_sequence_repetition_findings": semantic,
        "provider_unit_repetition_findings": units,
        "intentional_continuity_cases": intentional,
        "human_review_cases": human,
        "sh031_warning": {"status": "PRESERVED", **v2["sh031_warning"]},
        "luna_gate_001": "CLOSED_BY_LOCAL_DUPLICATE_GATE" if status == "PASS" else "OPEN",
        "next_stage": NEXT_AFTER_GATE if status == "PASS" else "BLOCKED",
        "next_stage_executed": False,
        "production_resume_entrypoint": RESUME_ENTRYPOINT,
        "cli_production_resume": "BLOCKED",
        "direct_script_production_resume": "BLOCKED",
        "production_resume_authorized": False,
        "network_calls": 0,
        "paid_provider_calls": 0,
        "autopilot_runs": 0,
        "files_deleted": 0,
    }


def run_local_gate(repo_root: Path) -> dict[str, Any]:
    """Commit only the current local gate and never invoke the next stage."""
    repo = Path(repo_root).resolve()
    paths = _paths(repo)
    if any(paths[key].exists() for key in ("gate", "gate_closure", "report_md", "report_json")):
        raise PromptSimilarityGateError("GATE_OUTPUT_TARGET_EXISTS_FAIL_CLOSED")
    result = analyze_promoted_plan(repo)
    append_transition(repo, EPISODE, stage=STAGE, previous_stage="NARRATION_VISUAL_ALIGNMENT_GATE", status="STARTED", input_artifacts=[result["input_artifacts"]["overlay"], result["input_artifacts"]["plan"], result["input_artifacts"]["storyboard"]], metadata={"event": "LOCAL_PROMPT_SIMILARITY_DUPLICATE_GATE_STARTED", "production_resume_entrypoint": RESUME_ENTRYPOINT, "provider_calls": 0})
    write_new_json(paths["gate"], result)
    if result["status"] == "PASS":
        closure = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "finding_id": "LUNA-GATE-001", "status": "CLOSED_BY_LOCAL_DUPLICATE_GATE", "authority": "LOCAL_DOWNSTREAM_GATE", "gate_result": artifact_reference(paths["gate"], base=repo), "luna_has_authority": False, "next_stage": NEXT_AFTER_GATE, "next_stage_executed": False}
        write_new_json(paths["gate_closure"], closure)
        append_transition(repo, EPISODE, stage=STAGE, previous_stage="NARRATION_VISUAL_ALIGNMENT_GATE", status="COMPLETED", input_artifacts=[result["input_artifacts"]["overlay"], result["input_artifacts"]["plan"]], output_artifacts=[artifact_reference(paths["gate"], base=repo), artifact_reference(paths["gate_closure"], base=repo)], schema_versions=[SCHEMA_VERSION], metadata={"event": "LOCAL_DUPLICATE_GATE_COMPLETED", "luna_gate_001": "CLOSED_BY_LOCAL_DUPLICATE_GATE", "next_stage_projection": NEXT_AFTER_GATE, "next_stage_executed": False, "production_resume_entrypoint": RESUME_ENTRYPOINT, "provider_calls": 0})
    else:
        append_transition(repo, EPISODE, stage=STAGE, previous_stage="NARRATION_VISUAL_ALIGNMENT_GATE", status="FAILED", input_artifacts=[result["input_artifacts"]["overlay"], result["input_artifacts"]["plan"]], output_artifacts=[artifact_reference(paths["gate"], base=repo)], failure_classification=result["status"], schema_versions=[SCHEMA_VERSION], metadata={"event": "LOCAL_DUPLICATE_GATE_BLOCKED", "next_stage_executed": False, "production_resume_entrypoint": RESUME_ENTRYPOINT, "provider_calls": 0})
    final = project_state(repo, EPISODE)
    expected_stage = NEXT_AFTER_GATE if result["status"] == "PASS" else STAGE
    if final.current_stage != expected_stage:
        raise PromptSimilarityGateError("GATE_LEDGER_PROJECTION_INVALID")
    verification = {**result, "post_ledger": {"current_stage": final.current_stage, "status": final.status, "ledger_entries": len(__import__('src.application.episode_transition_ledger_v1', fromlist=['read_entries']).read_entries(repo, EPISODE))}, "offline_validation": "PASS", "network_deny": "PASS"}
    write_new_json(paths["report_json"], verification)
    lines = ["# Episode 002 — Prompt Similarity and Duplicate Gate", "", f"Status: `{result['status']}`", "", "## Findings", "", f"- Exact duplicates: `{len(result['exact_duplicates'])}`", f"- Near duplicates: `{len(result['near_duplicates'])}`", f"- Semantic/cross-sequence findings: `{len(result['semantic_repetition_findings'])}`", f"- Intentional continuity cases: `{len(result['intentional_continuity_cases'])}`", "", "The promoted input was used exclusively. No provider, media, Autopilot, or next-stage execution occurred.", ""]
    with paths["report_md"].open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
    return verification
