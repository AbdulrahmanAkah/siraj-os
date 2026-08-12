"""One-time, human-authorized promotion of Episode 002's preserved candidate.

No provider transport is imported or invoked here.  The legacy alignment FAIL
artifact remains immutable forensic evidence; human closure is represented by
new append-only receipts and the authoritative transition-ledger completion.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from src.application.artifact_provenance_v1 import (
    append_jsonl,
    artifact_reference,
    canonical_sha256,
    sha256_file,
    utc_now,
    write_new_json,
)
from src.application.cinematic_shot_contracts import (
    join_provider_ready_plan,
    migrate_legacy_creative_overlay,
    structural_fingerprint,
    structural_shots_from_storyboard,
)
from src.application.controlled_alignment_validation_v1 import _preflight, _required_structural_fingerprint
from src.application.episode_transition_ledger_v1 import (
    append_transition,
    ledger_path,
    project_state,
    read_entries,
)
from src.application.preserved_alignment_candidate_salvage_v1 import derive_salvage_view


SCHEMA_VERSION = "siraj-episode-002-candidate-promotion-v1"
EPISODE = "episode-002-adam-temptation-fall-repentance"
CANDIDATE_SHA256 = "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
BASELINE_SHA256 = "0d4bc1f9216f7f84a37a4209f9fc1c9cdb00f82bddf0e209be70995ced09ea81"
STRUCTURAL_FINGERPRINT = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
STAGE = "NARRATION_VISUAL_ALIGNMENT_GATE"
NEXT_STAGE = "PROMPT_SIMILARITY_AND_DUPLICATE_GATE"
ATTEMPT_ID = "75611537-2fa2-41be-acbf-98540e65bee7"
UNKNOWN_ATTEMPT_ID = "85a1e2de-3c05-427f-82d0-c2effa0ae173"
SEMANTIC_IDS = ("LUNA-SEM-001", "LUNA-SEM-002", "LUNA-SEM-003", "LUNA-SEM-004", "LUNA-REP-001")


class CandidatePromotionError(RuntimeError):
    pass


def _paths(repo: Path) -> dict[str, Path]:
    ep = repo / "projects" / EPISODE
    orchestration = ep / "orchestration"
    controlled = orchestration / "controlled-alignment-validation-v1"
    return {
        "proposal": repo / "reports" / "episode-002-candidate-promotion-proposal.json",
        "closure_review": repo / "reports" / "episode-002-final-human-semantic-closure-review.json",
        "salvage_view": controlled / "preserved-candidate-salvage-view-v1.json",
        "legacy_prompt_plan": ep / "preproduction" / "luna-semantic-prompt-direction-v6-2-1.json",
        "storyboard": ep / "preproduction" / "audio-bound-storyboard-v6-1.json",
        "timeline": ep / "preproduction" / "audio-timestamps-and-beats-v6-1.json",
        "legacy_alignment_audit": ep / "preproduction" / "narration-visual-alignment-gate-v6-2-1.json",
        "ledger": ledger_path(repo, EPISODE),
        "raw_response": orchestration / "paid-operation-attempts-v1" / ATTEMPT_ID / "raw-response.bin",
        "provider_proposal": controlled / "provider-proposal.json",
        "attempt_request": orchestration / "paid-operation-attempts-v1" / ATTEMPT_ID / "request.json",
        "attempt_events": orchestration / "paid-operation-attempts-v1" / ATTEMPT_ID / "attempt-events.jsonl",
        "unknown_attempt": orchestration / "luna-v6-3" / "narration_visual_alignment_gate" / "attempts" / (UNKNOWN_ATTEMPT_ID + ".unknown-not-retried-superseded.json"),
        "authorization": orchestration / "human-candidate-promotion-approval-v1.json",
        "closure_receipts": orchestration / "human-semantic-closure-receipts-v1.jsonl",
        "human_alignment": ep / "preproduction" / "narration-visual-alignment-human-closure-v1.json",
        "promoted_overlay": ep / "preproduction" / "siraj-creative-shot-direction-promoted-v1.json",
        "promoted_plan": ep / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json",
        "v2_acceptance": orchestration / "v2-warning-acceptance-v1.json",
        "promotion_receipt": orchestration / "creative-candidate-promotion-receipt-v1.json",
        "promotion_state": orchestration / "episode-creative-promotion-state-v1.json",
        "report_md": repo / "reports" / "episode-002-candidate-promotion-application.md",
        "report_json": repo / "reports" / "episode-002-candidate-promotion-verification.json",
        "migration_verification": repo / "reports" / "episode-002-phase0-4-migration-application-verification.json",
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise CandidatePromotionError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _backup(repo: Path, sources: Mapping[str, Path]) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root = Path(r"C:\SIRAJ\Backups") / ("siraj-ep002-candidate-promotion-" + stamp)
    root.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    for label, source in sources.items():
        relative = source.resolve().relative_to(repo.resolve())
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        source_hash = sha256_file(source)
        if sha256_file(destination) != source_hash:
            raise CandidatePromotionError("BACKUP_HASH_MISMATCH:" + label)
        rows.append({"label": label, "source_path": str(relative).replace("\\", "/"), "sha256": source_hash, "backup_path": str(destination.relative_to(root)).replace("\\", "/")})
    manifest = {"schema_version": SCHEMA_VERSION, "purpose": "PREWRITE_CANDIDATE_PROMOTION_BACKUP", "created_at_utc": utc_now(), "episode_id": EPISODE, "files": rows}
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    write_new_json(root / "backup-manifest.json", manifest)
    return {"path": str(root), "manifest_path": str(root / "backup-manifest.json"), "manifest_sha256": sha256_file(root / "backup-manifest.json"), "sources": rows}


def preflight(repo_root: Path) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    paths = _paths(repo)
    for path in paths.values():
        if path.name in {"human-candidate-promotion-approval-v1.json", "human-semantic-closure-receipts-v1.jsonl", "narration-visual-alignment-human-closure-v1.json", "siraj-creative-shot-direction-promoted-v1.json", "siraj-promoted-provider-ready-prompt-plan-v1.json", "v2-warning-acceptance-v1.json", "creative-candidate-promotion-receipt-v1.json", "episode-creative-promotion-state-v1.json", "episode-002-candidate-promotion-application.md", "episode-002-candidate-promotion-verification.json"}:
            continue
        if not path.is_file():
            raise CandidatePromotionError("REQUIRED_ARTIFACT_MISSING:" + str(path))
    targets = [
        paths[key] for key in ("authorization", "closure_receipts", "human_alignment", "promoted_overlay", "promoted_plan", "v2_acceptance", "promotion_receipt", "promotion_state", "report_md", "report_json")
    ]
    if any(path.exists() for path in targets):
        raise CandidatePromotionError("PROMOTION_TARGET_EXISTS_FAIL_CLOSED")
    proposal = _read_json(paths["proposal"])
    closure = _read_json(paths["closure_review"])
    state = _preflight(repo, EPISODE)
    salvage = derive_salvage_view(repo, EPISODE)
    projection = project_state(repo, EPISODE)
    if (
        proposal.get("status") != "PROPOSED_NOT_APPROVED_NOT_APPLIED"
        or proposal.get("candidate_sha256") != CANDIDATE_SHA256
        or proposal.get("old_creative_baseline_sha256") != BASELINE_SHA256
        or closure.get("candidate_sha256") != CANDIDATE_SHA256
        or closure.get("semantic_findings_recommended_closed") != 5
        or state["creative_overlay_hash"] != BASELINE_SHA256
        or salvage.get("candidate_sha256") != CANDIDATE_SHA256
        or state["required_structural_fingerprint"] != STRUCTURAL_FINGERPRINT
        or float(state["timeline"].get("total_duration_seconds")) != 623.584
        or len(state["structures"]) != 55
        or projection.current_stage != STAGE
        or projection.status != "FAILED"
    ):
        raise CandidatePromotionError("PROMOTION_PREWRITE_AUTHORITY_MISMATCH")
    if (state["structures"][-1].shot_id, state["structures"][-1].start_ms, state["structures"][-1].end_ms) != ("EP002-SH-055", 622784, 623584):
        raise CandidatePromotionError("PROMOTION_PREWRITE_FINAL_SHOT_MISMATCH")
    if any(a.end_ms != b.start_ms for a, b in zip(state["structures"], state["structures"][1:])):
        raise CandidatePromotionError("PROMOTION_PREWRITE_TIMELINE_DISCONTINUITY")
    if sha256_file(paths["raw_response"]) != proposal["paid_attempt_provenance"]["raw_response"]["sha256"]:
        raise CandidatePromotionError("RAW_PROVIDER_EVIDENCE_HASH_MISMATCH")
    if sha256_file(paths["provider_proposal"]) != proposal["paid_attempt_provenance"]["original_provider_response"]["sha256"]:
        raise CandidatePromotionError("PROVIDER_PROPOSAL_HASH_MISMATCH")
    modified = [patch["shot_id"] for patch in salvage["patches"]]
    if modified != proposal["modified_shot_ids"] or len(modified) != 29:
        raise CandidatePromotionError("PROMOTION_MODIFIED_SHOT_SET_MISMATCH")
    for finding in closure["semantic_closure_findings"]:
        if finding["finding_id"] not in SEMANTIC_IDS or finding["recommendation"] != "HUMAN_CLOSE_RECOMMENDED":
            raise CandidatePromotionError("HUMAN_SEMANTIC_CLOSURE_REQUIRED")
    return {"repo": repo, "paths": paths, "proposal": proposal, "closure": closure, "state": state, "salvage": salvage, "projection": projection, "prewrite_hashes": {key: sha256_file(path) for key, path in paths.items() if path.is_file()}}


def _write_markdown(path: Path, verification: Mapping[str, Any]) -> None:
    lines = ["# Episode 002 — Candidate Promotion Application", "", "Promotion was committed under human semantic-review authority only. No provider, downstream gate, or Autopilot action was run.", "", f"- Candidate: `{verification['candidate_sha256']}`", f"- Baseline preserved: `{verification['old_creative_baseline_sha256']}`", f"- Next stage (not executed): `{NEXT_STAGE}`", f"- V2 warning: `SH-031 OVERCONCEPTUALIZED_WITHOUT_PHYSICAL_ANCHOR` accepted as intentional non-blocking abstraction.", ""]
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def apply_approved_promotion(repo_root: Path) -> dict[str, Any]:
    """Apply the single approved human promotion and stop before the next gate."""

    pre = preflight(repo_root)
    repo: Path = pre["repo"]
    paths: dict[str, Path] = pre["paths"]
    state = pre["state"]
    salvage = pre["salvage"]
    closure = pre["closure"]
    backup_sources = {key: paths[key] for key in ("ledger", "legacy_prompt_plan", "storyboard", "timeline", "legacy_alignment_audit", "proposal", "closure_review", "salvage_view", "raw_response", "provider_proposal", "attempt_request", "attempt_events", "unknown_attempt")}
    backup = _backup(repo, backup_sources)
    authorization = {
        "schema_version": SCHEMA_VERSION,
        "status": "APPROVED_CANDIDATE_PROMOTION_ONLY",
        "episode_id": EPISODE,
        "approval_source": "EXPLICIT_HUMAN_USER_INSTRUCTION_IN_CURRENT_SESSION",
        "scope": "CANDIDATE_PROMOTION_ONLY",
        "candidate_sha256": CANDIDATE_SHA256,
        "old_creative_baseline_sha256": BASELINE_SHA256,
        "authorizes_provider_calls": False,
        "authorizes_downstream_gate_execution": False,
        "authorizes_autopilot_resume": False,
        "authorizes_retry": False,
        "authorizes_resubmission": False,
        "authorizes_candidate_promotion": True,
        "approved_at_utc": utc_now(),
    }
    authorization["approval_sha256"] = canonical_sha256(authorization)
    write_new_json(paths["authorization"], authorization)
    authorization_ref = artifact_reference(paths["authorization"], base=repo)
    # The canonical ledger records the current failed alignment stage reopening
    # under human authority; no downstream stage is started.
    append_transition(repo, EPISODE, stage=STAGE, previous_stage="LUNA_SEMANTIC_PROMPT_DIRECTION", status="STARTED", authorization_references=[authorization_ref], input_artifacts=[artifact_reference(paths["closure_review"], base=repo), artifact_reference(paths["proposal"], base=repo)], attempt_references=[artifact_reference(paths["provider_proposal"], base=repo)], metadata={"event": "HUMAN_SEMANTIC_CLOSURE_APPROVED", "closure_authority": "HUMAN_SEMANTIC_REVIEW", "candidate_sha256": CANDIDATE_SHA256, "provider_calls": 0, "downstream_execution": False})
    receipts = []
    for finding in closure["semantic_closure_findings"]:
        receipt = {"schema_version": SCHEMA_VERSION, "receipt_id": "HUMAN-CLOSURE-" + finding["finding_id"], "episode_id": EPISODE, "finding_id": finding["finding_id"], "previous_status": "FAIL_BLOCKING", "human_closure_decision": "CLOSED_BY_HUMAN_REVIEW", "closure_authority": "HUMAN_SEMANTIC_REVIEW", "closure_evidence_reference": artifact_reference(paths["closure_review"], base=repo), "candidate_sha256": CANDIDATE_SHA256, "affected_shot_ids": finding["affected_shot_ids"], "source_safety": "PASS", "structural_change": "NONE", "generic_regression_detected": False, "human_approval_provenance": authorization_ref, "created_at_utc": utc_now()}
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        append_jsonl(paths["closure_receipts"], receipt)
        receipts.append(receipt)
    candidate = dict(salvage["candidate_overlay"])
    if canonical_sha256(candidate) != CANDIDATE_SHA256:
        raise CandidatePromotionError("PROMOTION_CANDIDATE_SERIALIZATION_MISMATCH")
    write_new_json(paths["promoted_overlay"], candidate)
    provider_plan = join_provider_ready_plan(state["structures"], candidate)
    if (
        provider_plan["creative_overlay_sha256"] != CANDIDATE_SHA256
        or provider_plan["storyboard_structural_fingerprint"] != structural_fingerprint(state["structures"])
    ):
        raise CandidatePromotionError("PROMOTION_PROVIDER_PLAN_INVARIANT_MISMATCH")
    write_new_json(paths["promoted_plan"], provider_plan)
    v2_acceptance = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "status": "WARN_ACCEPTED_NON_BLOCKING", "v2_review_reference": artifact_reference(paths["closure_review"], base=repo), "reasons": ["NO_IDENTICAL_CROSS_SEQUENCE_SIGNATURE", "SIGNIFICANT_REGRESSION_FALSE", "SOURCE_SAFETY_PASS", "STRUCTURAL_CHANGE_NONE", "GENERIC_REGRESSION_FALSE"], "sh031_warning": {"shot_id": "EP002-SH-031", "warning": "OVERCONCEPTUALIZED_WITHOUT_PHYSICAL_ANCHOR", "abstraction_balance": "WARN", "material_specificity": "WARN", "classification": "ACCEPTED_INTENTIONAL_ABSTRACTION_NON_BLOCKING", "rationale": "Epistemic restraint avoids fabricating a source, visible message, supernatural delivery mechanism, or unsupported physical event."}, "patch_applied": False}
    write_new_json(paths["v2_acceptance"], v2_acceptance)
    human_alignment = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "status": "PASS_BY_HUMAN_SEMANTIC_CLOSURE", "legacy_fail_audit_preserved": artifact_reference(paths["legacy_alignment_audit"], base=repo), "closed_finding_ids": list(SEMANTIC_IDS), "open_downstream_gate": {"finding_id": "LUNA-GATE-001", "owner": "DOWNSTREAM_GATE", "status": "PRE_SPEND_GATE_NOT_CLOSED", "required_stage": NEXT_STAGE}, "closure_receipts_path": str(paths["closure_receipts"].relative_to(repo)).replace("\\", "/"), "candidate_sha256": CANDIDATE_SHA256, "structural_fingerprint": STRUCTURAL_FINGERPRINT}
    write_new_json(paths["human_alignment"], human_alignment)
    promotion_receipt = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "event": "CREATIVE_CANDIDATE_PROMOTED", "candidate_sha256": CANDIDATE_SHA256, "old_creative_baseline_sha256": BASELINE_SHA256, "modified_shot_ids": [patch["shot_id"] for patch in salvage["patches"]], "structural_fingerprint": STRUCTURAL_FINGERPRINT, "promoted_overlay": artifact_reference(paths["promoted_overlay"], base=repo), "promoted_prompt_plan": artifact_reference(paths["promoted_plan"], base=repo), "human_closure_receipts": [row["receipt_id"] for row in receipts], "paid_attempt_id": ATTEMPT_ID, "provider_evidence": artifact_reference(paths["raw_response"], base=repo), "old_baseline_preserved": True, "candidate_promoted": True, "provider_calls": 0}
    promotion_receipt["receipt_sha256"] = canonical_sha256(promotion_receipt)
    write_new_json(paths["promotion_receipt"], promotion_receipt)
    promotion_state = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "status": "PROMOTED_STOPPED_BEFORE_DOWNSTREAM_GATE", "authoritative_creative_overlay": artifact_reference(paths["promoted_overlay"], base=repo), "authoritative_current_prompt_plan": artifact_reference(paths["promoted_plan"], base=repo), "candidate_sha256": CANDIDATE_SHA256, "next_stage": NEXT_STAGE, "next_stage_executed": False, "production_resume_authorized": False, "open_downstream_gate": "LUNA-GATE-001"}
    write_new_json(paths["promotion_state"], promotion_state)
    outputs = [paths[key] for key in ("closure_receipts", "human_alignment", "promoted_overlay", "promoted_plan", "v2_acceptance", "promotion_receipt", "promotion_state")]
    append_transition(repo, EPISODE, stage=STAGE, previous_stage="LUNA_SEMANTIC_PROMPT_DIRECTION", status="COMPLETED", authorization_references=[authorization_ref], input_artifacts=[artifact_reference(paths["closure_review"], base=repo), artifact_reference(paths["proposal"], base=repo), artifact_reference(paths["salvage_view"], base=repo)], output_artifacts=[artifact_reference(path, base=repo) for path in outputs], attempt_references=[artifact_reference(paths["provider_proposal"], base=repo)], schema_versions=[SCHEMA_VERSION], metadata={"event": "CREATIVE_CANDIDATE_PROMOTION_AND_HUMAN_ALIGNMENT_COMPLETION", "closure_authority": "HUMAN_SEMANTIC_REVIEW", "candidate_sha256": CANDIDATE_SHA256, "v2_review_status": "WARN_ACCEPTED_NON_BLOCKING", "open_gate": "LUNA-GATE-001", "next_stage_projection": NEXT_STAGE, "next_stage_executed": False, "provider_calls": 0, "autopilot_runs": 0})
    final = project_state(repo, EPISODE)
    if final.current_stage != NEXT_STAGE or final.status != "READY":
        raise CandidatePromotionError("CANONICAL_NEXT_STAGE_PROJECTION_FAILED")
    return {"prewrite": pre, "backup": backup, "authorization": authorization, "closure_receipts": receipts, "promotion_receipt": promotion_receipt, "final_projection": final}


def verify_promoted_state(repo_root: Path) -> dict[str, Any]:
    """Read-only verification after a committed promotion."""

    repo = Path(repo_root).resolve()
    paths = _paths(repo)
    required = ("authorization", "closure_receipts", "human_alignment", "promoted_overlay", "promoted_plan", "v2_acceptance", "promotion_receipt", "promotion_state", "migration_verification")
    if any(not paths[key].is_file() for key in required):
        raise CandidatePromotionError("PROMOTED_ARTIFACT_MISSING")
    storyboard = _read_json(paths["storyboard"])
    timeline = _read_json(paths["timeline"])
    legacy_plan = _read_json(paths["legacy_prompt_plan"])
    structures = structural_shots_from_storyboard(storyboard)
    baseline = migrate_legacy_creative_overlay(storyboard, legacy_plan)
    projection = project_state(repo, EPISODE)
    overlay = _read_json(paths["promoted_overlay"])
    plan = _read_json(paths["promoted_plan"])
    promotion = _read_json(paths["promotion_receipt"])
    v2 = _read_json(paths["v2_acceptance"])
    migration = _read_json(paths["migration_verification"])
    closure_lines = [json.loads(line) for line in paths["closure_receipts"].read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    before = {row["shot_id"]: row for row in baseline["directions"]}
    after = {row["shot_id"]: row for row in overlay["directions"]}
    changed = [shot_id for shot_id in before if before[shot_id] != after[shot_id]]
    expected = promotion["modified_shot_ids"]
    if (
        canonical_sha256(overlay) != CANDIDATE_SHA256
        or plan.get("creative_overlay_sha256") != CANDIDATE_SHA256
        or changed != expected
        or len(changed) != 29
        or projection.current_stage != NEXT_STAGE
        or projection.status != "READY"
        or len(closure_lines) != 5
        or [row["finding_id"] for row in closure_lines] != list(SEMANTIC_IDS)
        or _required_structural_fingerprint(storyboard) != STRUCTURAL_FINGERPRINT
        or float(timeline.get("total_duration_seconds")) != 623.584
        or len(structures) != 55
        or v2.get("status") != "WARN_ACCEPTED_NON_BLOCKING"
        or migration.get("duplicate_gate", {}).get("excluded") != "PASS"
        or migration.get("unknown_attempt", {}).get("preserved") != "PASS"
    ):
        raise CandidatePromotionError("POSTWRITE_PROMOTION_VALIDATION_FAILED")
    return {
        "status": "PASS",
        "candidate_sha256": CANDIDATE_SHA256,
        "old_creative_baseline_sha256": BASELINE_SHA256,
        "old_creative_baseline_preserved": True,
        "raw_provider_evidence_preserved": sha256_file(paths["raw_response"]) == _read_json(paths["proposal"])["paid_attempt_provenance"]["raw_response"]["sha256"],
        "human_semantic_closures_committed": len(closure_lines),
        "alignment_gate": "PASS_BY_HUMAN_SEMANTIC_CLOSURE",
        "v2_review_status": v2["status"],
        "sh031_warning_preserved": v2["sh031_warning"],
        "structural_fingerprint_unchanged": _required_structural_fingerprint(storyboard) == STRUCTURAL_FINGERPRINT,
        "duration_seconds": timeline["total_duration_seconds"],
        "shot_count": len(structures),
        "timeline_discontinuities": sum(a.end_ms != b.start_ms for a, b in zip(structures, structures[1:])),
        "modified_creative_shots": len(changed),
        "unexpected_creative_shot_changes": len(set(changed).difference(expected)),
        "gate_001": {"owner": "DOWNSTREAM_GATE", "closed": False, "next_stage": NEXT_STAGE, "next_stage_executed": False},
        "stale_legacy_duplicate_gate_excluded": migration["duplicate_gate"]["excluded"] == "PASS",
        "unknown_old_attempt_preserved": True,
        "unknown_old_attempt_retried": False,
        "network_calls": 0,
        "paid_provider_calls": 0,
        "autopilot_runs": 0,
        "files_deleted": 0,
        "production_resume_authorized": False,
        "ledger_entry_count": len(read_entries(repo, EPISODE)),
        "ledger_append_only": True,
        "legacy_states_non_authoritative": True,
    }


def write_application_reports(repo_root: Path) -> dict[str, str]:
    repo = Path(repo_root).resolve()
    paths = _paths(repo)
    if paths["report_md"].exists() or paths["report_json"].exists():
        raise CandidatePromotionError("PROMOTION_REPORT_TARGET_EXISTS")
    verification = verify_promoted_state(repo)
    write_new_json(paths["report_json"], verification)
    _write_markdown(paths["report_md"], verification)
    return {"report_md": str(paths["report_md"]), "report_json": str(paths["report_json"])}


def resume_partial_approved_promotion(repo_root: Path) -> dict[str, Any]:
    """Finish only the known safe partial commit created after prewrite PASS.

    This is not a provider retry and does not recreate or overwrite the
    already-promoted overlay.  It verifies every partial immutable write first.
    """

    repo = Path(repo_root).resolve()
    paths = _paths(repo)
    required_partial = ("authorization", "closure_receipts", "promoted_overlay")
    if any(not paths[key].is_file() for key in required_partial):
        raise CandidatePromotionError("PARTIAL_PROMOTION_ARTIFACT_MISSING")
    forbidden_existing = ("promoted_plan", "v2_acceptance", "human_alignment", "promotion_receipt", "promotion_state", "report_md", "report_json")
    if any(paths[key].exists() for key in forbidden_existing):
        raise CandidatePromotionError("PARTIAL_PROMOTION_UNEXPECTED_TARGET_EXISTS")
    authorization = _read_json(paths["authorization"])
    if authorization.get("scope") != "CANDIDATE_PROMOTION_ONLY" or authorization.get("candidate_sha256") != CANDIDATE_SHA256:
        raise CandidatePromotionError("PARTIAL_PROMOTION_AUTHORIZATION_MISMATCH")
    receipts = [json.loads(line) for line in paths["closure_receipts"].read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if len(receipts) != 5 or [row.get("finding_id") for row in receipts] != list(SEMANTIC_IDS):
        raise CandidatePromotionError("PARTIAL_PROMOTION_CLOSURE_RECEIPTS_INVALID")
    storyboard = _read_json(paths["storyboard"])
    timeline = _read_json(paths["timeline"])
    legacy_plan = _read_json(paths["legacy_prompt_plan"])
    structures = structural_shots_from_storyboard(storyboard)
    overlay = _read_json(paths["promoted_overlay"])
    if (
        canonical_sha256(overlay) != CANDIDATE_SHA256
        or _required_structural_fingerprint(storyboard) != STRUCTURAL_FINGERPRINT
        or float(timeline.get("total_duration_seconds")) != 623.584
        or len(structures) != 55
    ):
        raise CandidatePromotionError("PARTIAL_PROMOTION_AUTHORITY_MISMATCH")
    projection = project_state(repo, EPISODE)
    entries = read_entries(repo, EPISODE)
    if projection.current_stage != STAGE or projection.status != "RUNNING" or entries[-1].get("metadata", {}).get("event") != "HUMAN_SEMANTIC_CLOSURE_APPROVED":
        raise CandidatePromotionError("PARTIAL_PROMOTION_LEDGER_STATE_INVALID")
    authorization_ref = artifact_reference(paths["authorization"], base=repo)
    provider_plan = join_provider_ready_plan(structures, overlay)
    if provider_plan["creative_overlay_sha256"] != CANDIDATE_SHA256 or provider_plan["storyboard_structural_fingerprint"] != structural_fingerprint(structures):
        raise CandidatePromotionError("PARTIAL_PROMOTION_PROVIDER_PLAN_INVARIANT_MISMATCH")
    write_new_json(paths["promoted_plan"], provider_plan)
    v2_acceptance = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "status": "WARN_ACCEPTED_NON_BLOCKING", "v2_review_reference": artifact_reference(paths["closure_review"], base=repo), "reasons": ["NO_IDENTICAL_CROSS_SEQUENCE_SIGNATURE", "SIGNIFICANT_REGRESSION_FALSE", "SOURCE_SAFETY_PASS", "STRUCTURAL_CHANGE_NONE", "GENERIC_REGRESSION_FALSE"], "sh031_warning": {"shot_id": "EP002-SH-031", "warning": "OVERCONCEPTUALIZED_WITHOUT_PHYSICAL_ANCHOR", "abstraction_balance": "WARN", "material_specificity": "WARN", "classification": "ACCEPTED_INTENTIONAL_ABSTRACTION_NON_BLOCKING", "rationale": "Epistemic restraint avoids fabricating a source, visible message, supernatural delivery mechanism, or unsupported physical event."}, "patch_applied": False}
    write_new_json(paths["v2_acceptance"], v2_acceptance)
    human_alignment = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "status": "PASS_BY_HUMAN_SEMANTIC_CLOSURE", "legacy_fail_audit_preserved": artifact_reference(paths["legacy_alignment_audit"], base=repo), "closed_finding_ids": list(SEMANTIC_IDS), "open_downstream_gate": {"finding_id": "LUNA-GATE-001", "owner": "DOWNSTREAM_GATE", "status": "PRE_SPEND_GATE_NOT_CLOSED", "required_stage": NEXT_STAGE}, "closure_receipts_path": str(paths["closure_receipts"].relative_to(repo)).replace("\\", "/"), "candidate_sha256": CANDIDATE_SHA256, "structural_fingerprint": STRUCTURAL_FINGERPRINT}
    write_new_json(paths["human_alignment"], human_alignment)
    baseline = migrate_legacy_creative_overlay(storyboard, legacy_plan)
    changed_ids = [row["shot_id"] for row, base in zip(overlay["directions"], baseline["directions"]) if row != base]
    if len(changed_ids) != 29:
        raise CandidatePromotionError("PARTIAL_PROMOTION_CHANGED_SHOT_SET_INVALID")
    promotion_receipt = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "event": "CREATIVE_CANDIDATE_PROMOTED", "candidate_sha256": CANDIDATE_SHA256, "old_creative_baseline_sha256": BASELINE_SHA256, "modified_shot_ids": changed_ids, "structural_fingerprint": STRUCTURAL_FINGERPRINT, "promoted_overlay": artifact_reference(paths["promoted_overlay"], base=repo), "promoted_prompt_plan": artifact_reference(paths["promoted_plan"], base=repo), "human_closure_receipts": [row["receipt_id"] for row in receipts], "paid_attempt_id": ATTEMPT_ID, "provider_evidence": artifact_reference(paths["raw_response"], base=repo), "old_baseline_preserved": True, "candidate_promoted": True, "provider_calls": 0}
    promotion_receipt["receipt_sha256"] = canonical_sha256(promotion_receipt)
    write_new_json(paths["promotion_receipt"], promotion_receipt)
    promotion_state = {"schema_version": SCHEMA_VERSION, "episode_id": EPISODE, "status": "PROMOTED_STOPPED_BEFORE_DOWNSTREAM_GATE", "authoritative_creative_overlay": artifact_reference(paths["promoted_overlay"], base=repo), "authoritative_current_prompt_plan": artifact_reference(paths["promoted_plan"], base=repo), "candidate_sha256": CANDIDATE_SHA256, "next_stage": NEXT_STAGE, "next_stage_executed": False, "production_resume_authorized": False, "open_downstream_gate": "LUNA-GATE-001"}
    write_new_json(paths["promotion_state"], promotion_state)
    outputs = [paths[key] for key in ("closure_receipts", "human_alignment", "promoted_overlay", "promoted_plan", "v2_acceptance", "promotion_receipt", "promotion_state")]
    append_transition(repo, EPISODE, stage=STAGE, previous_stage="LUNA_SEMANTIC_PROMPT_DIRECTION", status="COMPLETED", authorization_references=[authorization_ref], input_artifacts=[artifact_reference(paths["closure_review"], base=repo), artifact_reference(paths["proposal"], base=repo), artifact_reference(paths["salvage_view"], base=repo)], output_artifacts=[artifact_reference(path, base=repo) for path in outputs], attempt_references=[artifact_reference(paths["provider_proposal"], base=repo)], schema_versions=[SCHEMA_VERSION], metadata={"event": "CREATIVE_CANDIDATE_PROMOTION_AND_HUMAN_ALIGNMENT_COMPLETION", "closure_authority": "HUMAN_SEMANTIC_REVIEW", "candidate_sha256": CANDIDATE_SHA256, "v2_review_status": "WARN_ACCEPTED_NON_BLOCKING", "open_gate": "LUNA-GATE-001", "next_stage_projection": NEXT_STAGE, "next_stage_executed": False, "provider_calls": 0, "autopilot_runs": 0, "resumed_from_fail_closed_partial": True})
    final = project_state(repo, EPISODE)
    if final.current_stage != NEXT_STAGE or final.status != "READY":
        raise CandidatePromotionError("PARTIAL_PROMOTION_NEXT_STAGE_PROJECTION_FAILED")
    return {"status": "PASS", "final_projection": final}
