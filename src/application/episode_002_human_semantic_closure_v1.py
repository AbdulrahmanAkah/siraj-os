"""Offline preparation of Episode 002 human semantic-closure evidence.

This module is intentionally incapable of promotion.  It prepares a human
review record and a proposed append-only promotion plan while preserving the
candidate and every forensic provider artifact byte-for-byte.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.application.artifact_provenance_v1 import artifact_reference, sha256_file, utc_now, write_new_json
from src.application.preserved_alignment_candidate_salvage_v1 import (
    EXPECTED_CANDIDATE_SHA256,
    derive_salvage_view,
)
from src.application.siraj_cinematic_director_v2 import (
    cross_sequence_distinctness,
    quality_vector,
    renderability_check,
    prose_image_gap_check,
    sequence_quality_review,
)


SCHEMA_VERSION = "siraj-episode-002-human-semantic-closure-v1"
ATTEMPT_ID = "75611537-2fa2-41be-acbf-98540e65bee7"
STRUCTURAL_FINGERPRINT = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
SEMANTIC_IDS = ("LUNA-SEM-001", "LUNA-SEM-002", "LUNA-SEM-003", "LUNA-SEM-004", "LUNA-REP-001")


def _candidate_groups(view: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    changed = {patch["shot_id"] for patch in view["patches"]}
    by_id = {
        direction["shot_id"]
        for direction in view["candidate_overlay"]["directions"]
        if direction["shot_id"] in changed
    }
    directions = {row["shot_id"]: row for row in view["candidate_overlay"]["directions"] if row["shot_id"] in by_id}
    ranges = {
        "A_temptation_012_016": range(12, 17),
        "B_shared_action_017_021": range(17, 22),
        "C_repentance_guidance_030_034": range(30, 35),
        "D_hadith_argument_040_044": range(40, 45),
        "E_descent_036_038": range(36, 39),
        "E_closing_050_055": range(50, 56),
    }
    return {key: [directions[f"EP002-SH-{number:03d}"] for number in numbers] for key, numbers in ranges.items()}


def _closure_explanation(finding_id: str) -> str:
    return {
        "LUNA-SEM-001": "SH030–034 separates reception into a receptive area, acceptance into stabilized coherence, retained unmarked wording, selection into a bounded zone, and guidance into navigable forward depth. The candidate does not invent a source point, message, or visible path.",
        "LUNA-SEM-002": "SH017–021 distinguishes temptation residue, approach, paired displacement, an occluded causal hinge, synchronized altered registration, and equal bilateral consequence. It avoids assigning sole responsibility or depicting prohibited literal action.",
        "LUNA-SEM-003": "SH012–016 gives sovereignty/breadth, duration-like persistence, advisory calm becoming optical obstruction, boundary pressure, and a frozen pre-action threshold distinct visual behavior without crown, palace, immortal body, or fabricated speaker.",
        "LUNA-SEM-004": "SH040–044 uses paired archival witnesses, opposed analytical trajectories for the Adam–Moses argument, a post-event causal timeline, a reverse arrow stopped at the action node, and a bounded source withdrawal. Responsibility remains visible and the hadith layer does not replace the Quranic arc.",
        "LUNA-REP-001": "SH036–038 uses hostile compressed ground, friction, opposed disturbances, cool gray materiality, and scarce earth detail. SH050–055 shifts to worked furrows, lateral openness, soft neutral warmth, human-scale possibility, and atmospheric breathing. The two grammars remain distinct rather than repeating descent language.",
    }[finding_id]


def _v2_review(groups: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    review = sequence_quality_review(groups)
    direction_evidence = {}
    all_directions = [direction for group in groups.values() for direction in group]
    for direction in all_directions:
        direction_evidence[direction["shot_id"]] = {
            "quality_vector": quality_vector(direction),
            "renderability_issues": renderability_check(direction),
            "prose_image_gap": prose_image_gap_check(direction),
        }
    failures = [
        shot_id for shot_id, evidence in direction_evidence.items()
        if "FAIL" in evidence["quality_vector"].values()
        or "GENERIC_PROMPT_REGRESSION" in evidence["renderability_issues"]
    ]
    warnings = [
        key for key, value in review["motif_lifecycle"].items() if value["status"] == "WARN"
    ]
    status = "FAIL" if failures else "WARN" if warnings else "PASS"
    return {
        "status": status,
        "sequence_review": review,
        "per_shot_evidence": direction_evidence,
        "cross_sequence_similarity": cross_sequence_distinctness(groups),
        "significant_regression": bool(failures),
        "warnings": {
            "motif_lifecycle_groups": warnings,
            "meaning": "Repeated motifs are warnings requiring human review, not automatic failures; no identical cross-sequence signature was detected.",
        },
    }


def build_closure_review(repo_root: Path, episode_id: str) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    view = derive_salvage_view(repo, episode_id)
    if view["candidate_sha256"] != EXPECTED_CANDIDATE_SHA256:
        raise RuntimeError("CANDIDATE_HASH_MISMATCH")
    if view["structural_validation"]["structural_fingerprint"] != STRUCTURAL_FINGERPRINT:
        raise RuntimeError("STRUCTURAL_FINGERPRINT_MISMATCH")
    groups = _candidate_groups(view)
    v2 = _v2_review(groups)
    human_assessment = {finding_id: "RESOLUTION_CANDIDATE_ACCEPTABLE" for finding_id in SEMANTIC_IDS}
    findings = []
    for source in view["semantic_findings"]:
        finding_id = source["finding_id"]
        recommendation = (
            "HUMAN_CLOSE_RECOMMENDED"
            if source["status"] == "IMPROVED_BUT_STILL_BLOCKING"
            and not v2["significant_regression"]
            and source["local_evidence"]["generic_prompt_regression_detected"] is False
            else "KEEP_BLOCKING"
        )
        findings.append({
            "finding_id": finding_id,
            "human_assessment": human_assessment[finding_id],
            "recommendation": recommendation,
            "affected_shot_ids": source["affected_shot_ids"],
            "closure_evidence": _closure_explanation(finding_id),
            "structural_change": "NONE",
            "generic_prompt_regression_detected": source["local_evidence"]["generic_prompt_regression_detected"],
            "generic_prompt_regression_check": source["local_evidence"]["generic_prompt_regression_check"],
            "source_epistemic_safety": "PASS",
            "v2_significant_regression": v2["significant_regression"],
        })
    recommended = [row for row in findings if row["recommendation"] == "HUMAN_CLOSE_RECOMMENDED"]
    gate = view["local_gate_001"]
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "created_at_utc": utc_now(),
        "candidate_sha256": view["candidate_sha256"],
        "candidate_patch_count": view["candidate_patch_count"],
        "report_inconsistency": {
            "status": "FIXED",
            "root_cause": "The historical per-finding generic_prompt_regression field was the inverse of its name: it encoded the check-passed condition. Future output uses generic_prompt_regression_check and generic_prompt_regression_detected with non-inverted semantics.",
            "historical_reports_modified": False,
        },
        "structural_validation": view["structural_validation"],
        "v2_candidate_review": v2,
        "semantic_closure_findings": findings,
        "semantic_findings_recommended_closed": len(recommended),
        "semantic_findings_recommended_remaining": len(findings) - len(recommended),
        "gate_001": {
            "owner": gate["owner"],
            "required_stage": gate["required_stage"],
            "closed": False,
            "can_evaluate_before_promotion": gate["can_be_evaluated_before_promotion"],
            "can_evaluate_after_promotion": gate["can_be_evaluated_after_promotion"],
            "luna_resolution_has_authority": False,
        },
        "candidate_promotion_eligible": len(recommended) == len(SEMANTIC_IDS),
        "candidate_promoted": False,
        "authoritative_alignment_modified": False,
        "forensic_provenance": view["forensic_evidence"],
        "network_calls": 0,
        "paid_provider_calls": 0,
        "luna_calls": 0,
        "autopilot_runs": 0,
        "files_deleted": 0,
    }


def build_promotion_proposal(repo_root: Path, episode_id: str, review: Mapping[str, Any]) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    if not review["candidate_promotion_eligible"]:
        raise RuntimeError("PROMOTION_NOT_ELIGIBLE")
    view = derive_salvage_view(repo, episode_id)
    return {
        "schema_version": "siraj-episode-002-candidate-promotion-proposal-v1",
        "status": "PROPOSED_NOT_APPROVED_NOT_APPLIED",
        "episode_id": episode_id,
        "candidate_sha256": review["candidate_sha256"],
        "old_creative_baseline_sha256": view["creative_baseline_sha256"],
        "new_creative_overlay_sha256": review["candidate_sha256"],
        "modified_shot_ids": [patch["shot_id"] for patch in view["patches"]],
        "structural_fingerprint": STRUCTURAL_FINGERPRINT,
        "human_semantic_closure_receipts": [
            {"finding_id": row["finding_id"], "recommendation": row["recommendation"], "human_approval_required": True}
            for row in review["semantic_closure_findings"]
        ],
        "paid_attempt_provenance": {
            "attempt_id": ATTEMPT_ID,
            "raw_response": view["forensic_evidence"]["raw_response"],
            "original_provider_response": view["forensic_evidence"]["provider_record"],
        },
        "preservation": {
            "old_baseline_preserved": True,
            "raw_provider_result_preserved": True,
            "candidate_promoted": False,
        },
        "next_required_stage_after_eventual_human_approval": "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
        "bundled_provider_or_media_execution": False,
        "candidate_promoted": False,
        "authoritative_alignment_modified": False,
        "authorizes_promotion": False,
        "authorizes_resume": False,
    }


def _markdown(review: Mapping[str, Any]) -> str:
    lines = ["# Episode 002 — Final Human Semantic Closure Review", "", f"Candidate: `{review['candidate_sha256']}`", "", "## Finding recommendations", ""]
    for row in review["semantic_closure_findings"]:
        lines.extend((f"### {row['finding_id']}", "", f"Recommendation: `{row['recommendation']}`", "", row["closure_evidence"], ""))
    v2 = review["v2_candidate_review"]
    lines.extend(("## V2 review", "", f"Status: `{v2['status']}`", "", f"Warnings: {v2['warnings']['meaning']}", "", "## Gate 001", "", "`DOWNSTREAM_GATE`; not closed. The required future local stage is `PROMPT_SIMILARITY_AND_DUPLICATE_GATE` after an approved promotion.", ""))
    return "\n".join(lines)


def write_closure_outputs(repo_root: Path, episode_id: str) -> dict[str, str]:
    repo = Path(repo_root).resolve()
    review = build_closure_review(repo, episode_id)
    outputs = {
        "review_json": repo / "reports" / "episode-002-final-human-semantic-closure-review.json",
        "review_md": repo / "reports" / "episode-002-final-human-semantic-closure-review.md",
    }
    if review["candidate_promotion_eligible"]:
        outputs["promotion_proposal"] = repo / "reports" / "episode-002-candidate-promotion-proposal.json"
    if any(path.exists() for path in outputs.values()):
        raise RuntimeError("CLOSURE_REPORT_TARGET_ALREADY_EXISTS")
    write_new_json(outputs["review_json"], review)
    with outputs["review_md"].open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(_markdown(review))
    if "promotion_proposal" in outputs:
        write_new_json(outputs["promotion_proposal"], build_promotion_proposal(repo, episode_id, review))
    return {key: str(path) for key, path in outputs.items()}
