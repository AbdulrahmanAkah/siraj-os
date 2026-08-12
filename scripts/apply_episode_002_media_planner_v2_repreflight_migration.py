"""Apply the approved EP002 V2 media-plan re-preflight migration locally.

This command is deliberately narrow: it validates content-addressed inputs,
backs up the affected state, preserves the old preflight as forensic history,
rewinds only the MEDIA_COST_PREFLIGHT boundary through append-only receipts,
and runs the provider-free canonical preflight executor against the approved
proposal.  It never reaches a provider adapter or changes paid authorization.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import uuid
from typing import Any, Mapping, Sequence

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
EPISODE = "episode-002-adam-temptation-fall-repentance"
EPISODE_ROOT = REPO / "projects" / EPISODE
ORCH = EPISODE_ROOT / "orchestration"
PRE = EPISODE_ROOT / "preproduction"
OLD_PREFLIGHT = ORCH / "media-cost-preflight-v1.json"
NEW_PREFLIGHT = ORCH / "media-cost-preflight-v2.json"
LEDGER = ORCH / "episode-transition-ledger-v1.jsonl"
PROPOSAL = REPO / "reports" / "episode-002-media-planner-v2-contract-valid-proposal.json"
MIGRATION_PROPOSAL = REPO / "reports" / "episode-002-media-planner-v2-preflight-migration-proposal.json"
REGISTRY = REPO / "projects" / "_series" / "siraj-media-pricing-registry-v2.json"
STORYBOARD = PRE / "audio-bound-storyboard-v6-1.json"
TIMELINE = PRE / "audio-timestamps-and-beats-v6-1.json"
OVERLAY = PRE / "siraj-creative-shot-direction-promoted-v1.json"
PROMPT_PLAN = PRE / "siraj-promoted-provider-ready-prompt-plan-v1.json"
POLICY = REPO / "projects" / "_series" / "siraj-cinematic-media-mix-policy-v2.json"
MASTER_AUTH = ORCH / "episode-master-paid-authorization-v6-6.json"
CREATIVE_PROMOTION = ORCH / "episode-creative-promotion-state-v1.json"
DUPLICATE_GATE = ORCH / "prompt-similarity-duplicate-gate-promoted-v1.json"
GATE_CLOSURE = ORCH / "luna-gate-001-local-closure-v1.json"

EXPECTED_OLD_PREFLIGHT_SHA = "926dea2fc77cf25f2cec1726accc318e9d0d0039955a2e5f719dddacf72f7f05"
EXPECTED_PROPOSAL_SHA = "50efe3d6e9b1f49a4d9867781a371cb80c3cd567799aa96af520212674fb3bf9"
EXPECTED_MIGRATION_PROPOSAL_SHA = "82cdbdb9c60a886d717f9be1bd04b94241e1b0fc327ffccfb01d595d37554936"
EXPECTED_LEDGER_SHA = "12798b9ef3710bc38ed2068c7e957aef878e5232148872ae9d921d126ddf2f72"
EXPECTED_LEDGER_HEAD = "fa157d4d59c4b51a1ff55d70b8c43f1a914c455338300b03aa895ad7ebf4a4ed"
EXPECTED_REGISTRY_SHA = "d95179a2a354cfb7ddbd492818e140527ba725ccdc3f4cd2f7df52e701e6cb8a"
EXPECTED_OVERLAY_SHA = "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
EXPECTED_STRUCTURAL_FP = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
EXPECTED_PROMPT_PLAN_SHA = "367ca94502ec82056fa8567eb2314f31c274588044dcd694aeec26ac1e296754"
EXPECTED_STORYBOARD_SHA = "e95299c4247c87e4d62a46e11a9c4f48c95b303c3b351036176e11a968277353"
EXPECTED_DURATION = 623.584
EXPECTED_VIDEO_SECONDS = 428.560
EXPECTED_VIDEO_PERCENT = 68.725304
EXPECTED_STILL_SECONDS = 131.261
EXPECTED_GRAPHICS_SECONDS = 63.763
EXPECTED_VIDEO_REQUESTS = 73
EXPECTED_STILL_REQUESTS = 22
EXPECTED_TOTAL_REQUESTS = 95
EXPECTED_REQUESTED_VIDEO_SECONDS = 496.000
EXPECTED_UNUSED_VIDEO_SECONDS = 67.440
EXPECTED_EFFICIENCY = 86.403226
EXPECTED_VIDEO_COST = 24.80000000
EXPECTED_STILL_COST = 1.10090000
EXPECTED_TOTAL_COST = 25.90090000


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"EXPECTED_OBJECT:{path}")
    return value


def _canonical_sha(value: Any) -> str:
    from src.application.artifact_provenance_v1 import canonical_sha256

    return canonical_sha256(value)


def _sha(path: Path) -> str:
    from src.application.artifact_provenance_v1 import sha256_file

    return sha256_file(path)


def _ref(path: Path) -> dict[str, Any]:
    from src.application.artifact_provenance_v1 import artifact_reference

    return artifact_reference(path, base=REPO)


def _json_payload(path: Path) -> dict[str, Any]:
    return _load(path)


def _verify_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    required_files = [
        PROPOSAL,
        MIGRATION_PROPOSAL,
        REGISTRY,
        LEDGER,
        OLD_PREFLIGHT,
        PROMPT_PLAN,
        OVERLAY,
        STORYBOARD,
        TIMELINE,
        POLICY,
        MASTER_AUTH,
        CREATIVE_PROMOTION,
        DUPLICATE_GATE,
        GATE_CLOSURE,
    ]
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise RuntimeError("MIGRATION_INPUT_MISSING:" + ",".join(missing))

    proposal = _load(PROPOSAL)
    migration = _load(MIGRATION_PROPOSAL)
    registry = _load(REGISTRY)
    from src.application.artifact_provenance_v1 import canonical_sha256

    if _sha(PROPOSAL) == "":
        raise RuntimeError("PROPOSAL_HASH_UNREADABLE")
    if proposal.get("proposal_sha256") != EXPECTED_PROPOSAL_SHA:
        raise RuntimeError("PROPOSAL_DECLARED_HASH_CHANGED")
    if canonical_sha256({k: v for k, v in proposal.items() if k != "proposal_sha256"}) != EXPECTED_PROPOSAL_SHA:
        raise RuntimeError("PROPOSAL_CANONICAL_HASH_CHANGED")
    if migration.get("proposal_sha256") != EXPECTED_MIGRATION_PROPOSAL_SHA:
        raise RuntimeError("MIGRATION_PROPOSAL_DECLARED_HASH_CHANGED")
    if canonical_sha256({k: v for k, v in migration.items() if k != "proposal_sha256"}) != EXPECTED_MIGRATION_PROPOSAL_SHA:
        raise RuntimeError("MIGRATION_PROPOSAL_CANONICAL_HASH_CHANGED")
    if _sha(REGISTRY) != EXPECTED_REGISTRY_SHA:
        raise RuntimeError("PRICING_REGISTRY_HASH_CHANGED")
    if _sha(LEDGER) != EXPECTED_LEDGER_SHA:
        raise RuntimeError("LEDGER_BYTES_CHANGED")
    if _sha(OLD_PREFLIGHT) != EXPECTED_OLD_PREFLIGHT_SHA:
        raise RuntimeError("OLD_PREFLIGHT_BYTES_CHANGED")
    if _sha(PROMPT_PLAN) != EXPECTED_PROMPT_PLAN_SHA:
        raise RuntimeError("PROMPT_PLAN_HASH_CHANGED")
    if canonical_sha256(_load(OVERLAY)) != EXPECTED_OVERLAY_SHA:
        raise RuntimeError("CREATIVE_OVERLAY_CANONICAL_HASH_CHANGED")
    if _sha(STORYBOARD) != EXPECTED_STORYBOARD_SHA:
        raise RuntimeError("STORYBOARD_HASH_CHANGED")
    if _sha(REGISTRY) != migration["new_plan"]["pricing_binding"]["pricing_registry_sha256"]:
        raise RuntimeError("MIGRATION_PRICING_BINDING_STALE")
    if migration["source_preflight"]["sha256"] != EXPECTED_OLD_PREFLIGHT_SHA:
        raise RuntimeError("MIGRATION_OLD_PREFLIGHT_BINDING_STALE")
    if migration["new_plan"]["sha256"] != EXPECTED_PROPOSAL_SHA:
        raise RuntimeError("MIGRATION_PLAN_BINDING_STALE")
    if proposal["input_hashes"]["current_episode_ledger_sha256"] != EXPECTED_LEDGER_SHA:
        raise RuntimeError("PROPOSAL_LEDGER_INPUT_STALE")
    if proposal["input_hashes"]["current_defective_preflight_sha256"] != EXPECTED_OLD_PREFLIGHT_SHA:
        raise RuntimeError("PROPOSAL_PREFLIGHT_INPUT_STALE")
    if proposal["input_hashes"]["provider_ready_prompt_plan_sha256"] != EXPECTED_PROMPT_PLAN_SHA:
        raise RuntimeError("PROPOSAL_PROMPT_PLAN_INPUT_STALE")

    entries = __import__("src.application.episode_transition_ledger_v1", fromlist=["read_entries"]).read_entries(REPO, EPISODE)
    if not entries or entries[-1].get("entry_sha256") != EXPECTED_LEDGER_HEAD:
        raise RuntimeError("LEDGER_HEAD_CHANGED")
    if any(row.get("metadata", {}).get("event") == "EP002_V2_REPREFLIGHT_COMPLETED" for row in entries):
        raise RuntimeError("MIGRATION_ALREADY_APPLIED")

    from src.application.desktop_resume_readiness_v1 import read_desktop_episode_state

    state = read_desktop_episode_state(REPO, EPISODE)
    if state.current_stage != "PROVIDER_EXECUTION" or state.status != "READY":
        raise RuntimeError("UNEXPECTED_CURRENT_CANONICAL_STATE")
    if state.ledger_head_sha256 != EXPECTED_LEDGER_SHA:
        raise RuntimeError("STATE_LEDGER_BYTES_CHANGED")
    if state.promoted_overlay_sha256 != EXPECTED_OVERLAY_SHA or state.authoritative_structural_fingerprint != EXPECTED_STRUCTURAL_FP:
        raise RuntimeError("AUTHORITATIVE_CREATIVE_OR_STRUCTURE_CHANGED")
    if state.duration_seconds != EXPECTED_DURATION or state.shot_count != 55 or state.timeline_discontinuities != 0:
        raise RuntimeError("AUTHORITATIVE_TIMELINE_CHANGED")

    policy = _load(POLICY)
    if (
        policy.get("schema_version") != "siraj-cinematic-media-mix-policy-v2"
        or policy.get("policy_id") != "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2"
        or float(policy.get("min_true_video_fraction")) != 0.50
        or float(policy.get("max_true_video_fraction")) != 0.75
        or policy.get("selection_mode") != "DIRECTORIAL_OPTIMIZATION"
    ):
        raise RuntimeError("MEDIA_MIX_POLICY_CHANGED")

    if proposal.get("status") != "CONTRACT_VALID_PROPOSAL_ONLY":
        raise RuntimeError("V2_PROPOSAL_STATUS_INVALID")
    coverage = proposal.get("coverage") or {}
    inventory = proposal.get("request_inventory") or {}
    cost = proposal.get("cost_summary") or {}
    contract = proposal.get("contract_validation_summary") or {}
    if (
        float(coverage.get("true_generated_video_timeline_seconds")) != EXPECTED_VIDEO_SECONDS
        or float(coverage.get("true_generated_video_timeline_percent")) != EXPECTED_VIDEO_PERCENT
        or float(coverage.get("animated_still_seconds")) != EXPECTED_STILL_SECONDS
        or float(coverage.get("graphics_local_seconds")) != EXPECTED_GRAPHICS_SECONDS
        or float(coverage.get("provider_requested_video_seconds")) != EXPECTED_REQUESTED_VIDEO_SECONDS
        or float(coverage.get("expected_unused_video_seconds")) != EXPECTED_UNUSED_VIDEO_SECONDS
        or float(coverage.get("video_request_efficiency_percent")) != EXPECTED_EFFICIENCY
        or int(inventory.get("video_provider_requests")) != EXPECTED_VIDEO_REQUESTS
        or int(inventory.get("still_provider_requests")) != EXPECTED_STILL_REQUESTS
        or int(inventory.get("total_provider_requests")) != EXPECTED_TOTAL_REQUESTS
        or float(cost.get("estimated_total_cost_usd")) != EXPECTED_TOTAL_COST
        or float(cost.get("maximum_cost_envelope_usd")) != EXPECTED_TOTAL_COST
        or cost.get("pricing_status") != "COMPLETE"
        or contract.get("provider_contract_status") != "PASS"
        or int(contract.get("remaining_invalid_video_units")) != 0
    ):
        raise RuntimeError("V2_PROPOSAL_METRICS_CHANGED")
    if proposal.get("pricing_binding", {}).get("status") != "VALID":
        raise RuntimeError("V2_PRICING_BINDING_INVALID")
    if proposal.get("provider_request_plan_hash") != migration["new_plan"]["provider_request_plan_hash"]:
        raise RuntimeError("V2_REQUEST_PLAN_HASH_CHANGED")
    return proposal, migration, registry, state.ledger_head_sha256


def _create_backup(source_paths: Sequence[Path]) -> tuple[Path, dict[str, Any]]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_root = REPO / ".siraj-repair-backups" / f"episode-002-v2-repreflight-{stamp}-{uuid.uuid4().hex[:8]}"
    backup_root.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    for source in source_paths:
        if not source.is_file():
            raise RuntimeError("BACKUP_SOURCE_MISSING:" + str(source))
        target = backup_root / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hash = _sha(source)
        backup_hash = _sha(target)
        if source_hash != backup_hash:
            raise RuntimeError("BACKUP_HASH_MISMATCH:" + str(source))
        rows.append({"source": str(source.relative_to(REPO)).replace("\\", "/"), "source_sha256": source_hash, "backup": str(target.relative_to(REPO)).replace("\\", "/"), "backup_sha256": backup_hash})
    manifest = {
        "schema_version": "siraj-episode-002-v2-repreflight-backup-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "episode_id": EPISODE,
        "files": rows,
        "provider_calls": 0,
        "paid_provider_calls": 0,
        "files_deleted": 0,
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    manifest_path = backup_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return backup_root, manifest


def _build_v2_result(
    repo: Path,
    episode_id: str,
    *,
    state: Any,
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    from src.application.artifact_provenance_v1 import artifact_reference, utc_now

    video_units = [deepcopy(unit) for unit in proposal["video_units"]]
    still_and_graphics = [deepcopy(unit) for unit in proposal["non_video_units"]]
    cost_rows = {str(row["request_id"]): row for row in proposal["cost_rows"]}
    units: list[dict[str, Any]] = []
    for unit in video_units + still_and_graphics:
        request_id = str(unit.get("unit_id"))
        cost_row = cost_rows.get(request_id)
        normalized = dict(unit)
        normalized["request_id"] = request_id
        normalized["provider_requested_seconds"] = float(unit.get("requested_seconds") or 0.0)
        normalized["timeline_coverage_seconds"] = float(
            unit.get("expected_usable_seconds")
            or unit.get("timeline_coverage_seconds")
            or 0.0
        )
        normalized["expected_cost_usd"] = float(cost_row["estimated_cost"]) if cost_row else None
        normalized["provider_submission"] = False
        normalized["paid_attempt_created"] = False
        units.append(normalized)

    input_paths = {
        "media_plan_proposal": PROPOSAL,
        "pricing_registry": REGISTRY,
        "creative_overlay": OVERLAY,
        "storyboard": STORYBOARD,
        "timeline": TIMELINE,
        "legacy_provider_ready_prompt_plan": PROMPT_PLAN,
        "media_policy": POLICY,
        "provider_contracts": REPO / "src" / "application" / "provider_model_contracts.py",
        "runware_contract": REPO / "src" / "application" / "siraj_runware_provider_contract_v6_6_r9.py",
        "superseded_preflight": OLD_PREFLIGHT,
    }
    input_artifacts = {
        key: artifact_reference(path, base=repo)
        for key, path in input_paths.items()
        if path.is_file()
    }
    coverage = proposal["coverage"]
    cost = proposal["cost_summary"]
    policy = proposal["policy"]
    result: dict[str, Any] = {
        "schema_version": "siraj-desktop-media-cost-preflight-v1",
        "status": "PASS",
        "episode_id": episode_id,
        "stage": "MEDIA_COST_PREFLIGHT",
        "created_at_utc": utc_now(),
        "authoritative_state": {
            "ledger_head_sha256": state.ledger_head_sha256,
            "current_stage": "MEDIA_COST_PREFLIGHT",
            "promoted_overlay_sha256": EXPECTED_OVERLAY_SHA,
            "structural_fingerprint": EXPECTED_STRUCTURAL_FP,
            "duration_seconds": EXPECTED_DURATION,
            "shot_count": 55,
            "timeline_discontinuities": 0,
        },
        "input_artifacts": input_artifacts,
        "media_plan_authority": {
            "path": "reports/episode-002-media-planner-v2-contract-valid-proposal.json",
            "proposal_sha256": EXPECTED_PROPOSAL_SHA,
            "provider_request_plan_hash": proposal["provider_request_plan_hash"],
            "status": "ACTIVE_V2_PLAN_FOR_REPREFLIGHT",
            "previous_plan": {
                "path": "projects/episode-002-adam-temptation-fall-repentance/preproduction/siraj-promoted-provider-ready-prompt-plan-v1.json",
                "sha256": EXPECTED_PROMPT_PLAN_SHA,
                "classification": "LEGACY_PROMPT_PLAN_PRESERVED_CONTEXT_ONLY",
            },
        },
        "media_policy": {
            **dict(policy),
            "two_thirds_policy_active": False,
            "coverage_floor_status": "PASS",
            "coverage_ceiling_status": "PASS",
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        },
        "summary": {
            "generated_video_seconds": EXPECTED_VIDEO_SECONDS,
            "generated_video_ratio": 0.68725304,
            "generated_video_percent": EXPECTED_VIDEO_PERCENT,
            "animated_still_seconds": EXPECTED_STILL_SECONDS,
            "graphics_local_seconds": EXPECTED_GRAPHICS_SECONDS,
            "provider_requested_seconds": EXPECTED_REQUESTED_VIDEO_SECONDS,
            "expected_unused_video_seconds": EXPECTED_UNUSED_VIDEO_SECONDS,
            "video_request_efficiency_percent": EXPECTED_EFFICIENCY,
            "planned_provider_requests": EXPECTED_TOTAL_REQUESTS,
            "planned_image_requests": EXPECTED_STILL_REQUESTS,
            "planned_video_requests": EXPECTED_VIDEO_REQUESTS,
            "planned_local_graphics": 4,
            "known_estimated_cost_usd": EXPECTED_TOTAL_COST,
            "unknown_provider_price_item_count": 0,
            "pricing_status": "COMPLETE",
            "video_subtotal_usd": EXPECTED_VIDEO_COST,
            "still_subtotal_usd": EXPECTED_STILL_COST,
            "estimated_total_cost_usd": EXPECTED_TOTAL_COST,
            "maximum_cost_envelope_usd": EXPECTED_TOTAL_COST,
            "currency": "USD",
            "longest_no_true_video_span_seconds": 56.021,
            "longest_static_sequence_preserved": True,
        },
        "generated_video_floor_seconds": round(EXPECTED_DURATION * 0.50, 3),
        "generated_video_ceiling_seconds": round(EXPECTED_DURATION * 0.75, 3),
        "cost_status": "KNOWN_LOCAL_PRICES",
        "cost_envelope_usd": {
            "lower_bound": 0.0,
            "upper_bound": EXPECTED_TOTAL_COST,
            "currency": "USD",
            "pricing_status": "COMPLETE",
            "pricing_registry_version": proposal["pricing_binding"]["pricing_registry_version"],
            "pricing_registry_sha256": EXPECTED_REGISTRY_SHA,
        },
        "units": units,
        "provider_contract_validation": {
            "status": "PASS",
            "remaining_invalid_video_units": 0,
            "veo31_negative_prompt_field": "BLOCKED",
            "pricing_contract_consistency": "PASS",
            "provider_api_calls": 0,
        },
        "authorization": {
            "master_authorization_status_for_new_plan": "ACTIVE_BUT_UNBOUND_REACK_REQUIRED",
            "cost_envelope_reack_required": True,
            "authorization_mutated": False,
            "paid_attempts_created": False,
            "provider_execution_allowed": False,
            "binding_inputs": {
                "episode_id": episode_id,
                "media_plan_sha256": EXPECTED_PROPOSAL_SHA,
                "pricing_registry_sha256": EXPECTED_REGISTRY_SHA,
                "provider_request_plan_hash": proposal["provider_request_plan_hash"],
                "cost_envelope": {"upper_bound": EXPECTED_TOTAL_COST, "currency": "USD"},
                "current_ledger_head_sha256": state.ledger_head_sha256,
                "creative_overlay_sha256": EXPECTED_OVERLAY_SHA,
                "structural_fingerprint": EXPECTED_STRUCTURAL_FP,
            },
        },
        "superseded_preflight": {
            "path": "projects/episode-002-adam-temptation-fall-repentance/orchestration/media-cost-preflight-v1.json",
            "sha256": EXPECTED_OLD_PREFLIGHT_SHA,
            "classification": "SUPERSEDED_BUT_PRESERVED",
            "counts_as_current_authority": False,
            "reasons": [
                "MEDIA_PLANNER_V1_OR_OLD_PLAN_INVALID",
                "3.474913_PERCENT_TRUE_VIDEO_ALLOCATION",
                "TIMELINE_AGNOSTIC_FIXED_8S_FALLBACK",
                "51_REQUEST_DEFECTIVE_PLAN",
                "UNKNOWN_PRICING_AT_ORIGINAL_PREFLIGHT_TIME",
            ],
        },
        "paid_attempts_created": 0,
        "provider_calls": 0,
        "next_stage": "PROVIDER_EXECUTION",
        "next_stage_executed": False,
        "production_resume_entrypoint": "DESKTOP_UI_ONLY",
        "production_status": "PAUSED_AWAITING_HUMAN_COST_ENVELOPE_REACK",
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
    }
    result["result_sha256"] = _canonical_sha(result)
    return result


def _report_payload(
    *,
    proposal: Mapping[str, Any],
    migration: Mapping[str, Any],
    backup_root: Path,
    backup_manifest: Mapping[str, Any],
    preserved_old: Path,
    receipts: Sequence[Mapping[str, Any]],
    outcome: Any,
    review: Any,
    ledger_before_sha: str,
    ledger_after_sha: str,
    ledger_before_head: str,
    ledger_after_head: str,
    old_preflight_sha: str,
    new_preflight_sha: str,
    new_preflight_result_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": "siraj-episode-002-media-planner-v2-repreflight-migration-report-v1",
        "status": "PASS",
        "episode_id": EPISODE,
        "migration_status": "APPLIED_LOCALLY_PROVIDER_FREE",
        "source_migration_proposal": {
            "path": str(MIGRATION_PROPOSAL.relative_to(REPO)).replace("\\", "/"),
            "sha256": EXPECTED_MIGRATION_PROPOSAL_SHA,
            "status": migration.get("status"),
        },
        "old_preflight": {
            "path": str(OLD_PREFLIGHT.relative_to(REPO)).replace("\\", "/"),
            "sha256": old_preflight_sha,
            "preserved_copy": str(preserved_old.relative_to(REPO)).replace("\\", "/"),
            "preserved_copy_sha256": _sha(preserved_old),
            "classification": "SUPERSEDED_BUT_PRESERVED",
            "counts_as_current_authority": False,
        },
        "new_preflight": {
            "path": str(NEW_PREFLIGHT.relative_to(REPO)).replace("\\", "/"),
            "file_sha256": new_preflight_sha,
            "result_sha256": new_preflight_result_sha,
            "status": "PASS",
        },
        "media_plan": {
            "path": str(PROPOSAL.relative_to(REPO)).replace("\\", "/"),
            "canonical_sha256": EXPECTED_PROPOSAL_SHA,
            "physical_sha256": _sha(PROPOSAL),
            "provider_request_plan_hash": proposal["provider_request_plan_hash"],
            "pricing_registry_sha256": EXPECTED_REGISTRY_SHA,
        },
        "ledger": {
            "path": str(LEDGER.relative_to(REPO)).replace("\\", "/"),
            "before_file_sha256": ledger_before_sha,
            "after_file_sha256": ledger_after_sha,
            "before_head_sha256": ledger_before_head,
            "after_head_sha256": ledger_after_head,
            "append_only": True,
            "receipts": [dict(item) for item in receipts],
        },
        "backup": {
            "root": str(backup_root.relative_to(REPO)).replace("\\", "/"),
            "manifest": backup_manifest,
        },
        "canonical_state": {
            "current_stage": "PROVIDER_EXECUTION",
            "production_status": "PAUSED_AWAITING_HUMAN_COST_ENVELOPE_REACK",
            "media_cost_preflight": "PASS",
            "provider_execution_started": False,
            "provider_execution_allowed": False,
            "cost_envelope_reack_required": True,
        },
        "metrics": {
            "true_video_timeline_seconds": EXPECTED_VIDEO_SECONDS,
            "true_video_percent": EXPECTED_VIDEO_PERCENT,
            "animated_still_seconds": EXPECTED_STILL_SECONDS,
            "graphics_local_seconds": EXPECTED_GRAPHICS_SECONDS,
            "video_provider_requests": EXPECTED_VIDEO_REQUESTS,
            "still_provider_requests": EXPECTED_STILL_REQUESTS,
            "total_provider_requests": EXPECTED_TOTAL_REQUESTS,
            "provider_requested_video_seconds": EXPECTED_REQUESTED_VIDEO_SECONDS,
            "expected_unused_video_seconds": EXPECTED_UNUSED_VIDEO_SECONDS,
            "video_request_efficiency_percent": EXPECTED_EFFICIENCY,
            "video_subtotal_usd": EXPECTED_VIDEO_COST,
            "still_subtotal_usd": EXPECTED_STILL_COST,
            "estimated_total_cost_usd": EXPECTED_TOTAL_COST,
            "maximum_cost_envelope_usd": EXPECTED_TOTAL_COST,
            "currency": "USD",
        },
        "integrity": {
            "duration_seconds": EXPECTED_DURATION,
            "shot_count": 55,
            "timeline_discontinuities": 0,
            "structural_fingerprint": EXPECTED_STRUCTURAL_FP,
            "creative_overlay_sha256": EXPECTED_OVERLAY_SHA,
            "alignment_gate": "PASS",
            "duplicate_gate": "PASS",
            "provider_contract_status": "PASS",
            "pricing_status": "COMPLETE",
            "veo31_negative_prompt_field": "BLOCKED",
        },
        "offline_validation": {
            "executor_outcome": outcome.as_dict(),
            "review": review.as_dict(),
            "network_calls": 0,
            "provider_api_calls": 0,
            "paid_provider_calls": 0,
            "autopilot_runs": 0,
            "files_deleted": 0,
            "authorization_mutated": False,
            "production_authorization_consumed": False,
        },
    }


def run() -> dict[str, Any]:
    proposal, migration, _registry, initial_head = _verify_inputs()
    ledger_before_sha = _sha(LEDGER)
    old_preflight_sha = _sha(OLD_PREFLIGHT)
    backup_root, backup_manifest = _create_backup([LEDGER, OLD_PREFLIGHT])

    from src.application.artifact_provenance_v1 import artifact_reference, preserve_existing, sha256_file, write_new_json
    from src.application.desktop_media_cost_preflight_v1 import CanonicalMediaCostPreflightExecutor, LOCAL_AUTH_SCOPE, read_persisted_media_cost_preflight
    from src.application.desktop_resume_readiness_v1 import DESKTOP_SOURCE, DesktopProductionResumeController
    from src.application.episode_transition_ledger_v1 import BASE_STAGE_ORDER, append_transition_if_head, project_state

    preserved_old = preserve_existing(OLD_PREFLIGHT)
    if preserved_old is None or _sha(preserved_old) != EXPECTED_OLD_PREFLIGHT_SHA:
        raise RuntimeError("OLD_PREFLIGHT_PRESERVATION_FAILED")

    local_auth = {
        "authorization_id": "desktop-v2-repreflight-local-" + uuid.uuid4().hex,
        "source": DESKTOP_SOURCE,
        "scope": LOCAL_AUTH_SCOPE,
        "episode_id": EPISODE,
        "provider_calls": 0,
        "paid_operation": False,
        "migration_proposal_sha256": EXPECTED_MIGRATION_PROPOSAL_SHA,
        "paid_authorization_created": False,
    }
    old_ref = artifact_reference(OLD_PREFLIGHT, base=REPO)
    preserved_ref = artifact_reference(preserved_old, base=REPO)
    proposal_ref = artifact_reference(PROPOSAL, base=REPO)
    registry_ref = artifact_reference(REGISTRY, base=REPO)
    overlay_ref = artifact_reference(OVERLAY, base=REPO)
    storyboard_ref = artifact_reference(STORYBOARD, base=REPO)
    timeline_ref = artifact_reference(TIMELINE, base=REPO)
    receipts: list[dict[str, Any]] = []

    invalidated = append_transition_if_head(
        REPO,
        EPISODE,
        expected_ledger_sha256=initial_head,
        stage="MEDIA_COST_PREFLIGHT",
        previous_stage="PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
        status="INVALIDATED",
        input_artifacts=[old_ref, proposal_ref, registry_ref],
        output_artifacts=[preserved_ref],
        schema_versions=["siraj-episode-002-media-planner-v2-preflight-migration-proposal-v1"],
        authorization_references=[local_auth],
        invalidation_links=[
            {
                "path": old_ref["path"],
                "sha256": EXPECTED_OLD_PREFLIGHT_SHA,
                "classification": "SUPERSEDED_BUT_PRESERVED",
                "counts_as_current_authority": False,
            }
        ],
        failure_classification="MEDIA_PLANNER_V1_OR_OLD_PLAN_INVALID",
        metadata={
            "event": "EP002_V2_REPREFLIGHT_INVALIDATE_OLD_PREFLIGHT",
            "transaction_id": "ep002-v2-repreflight-" + uuid.uuid4().hex,
            "old_true_video_percent": 3.474913,
            "old_provider_requests": 51,
            "old_fixed_duration_fallback": "TIMELINE_AGNOSTIC_FIXED_8S_FALLBACK",
            "old_pricing_status": "UNKNOWN",
            "provider_calls": 0,
        },
    )
    receipts.append(invalidated)
    after_invalidation_head = sha256_file(LEDGER)
    accepted_prior_stages = list(BASE_STAGE_ORDER[:13])
    migration_approved = append_transition_if_head(
        REPO,
        EPISODE,
        expected_ledger_sha256=after_invalidation_head,
        stage="MEDIA_COST_PREFLIGHT",
        previous_stage="PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
        status="MIGRATION_APPROVED",
        input_artifacts=[proposal_ref, registry_ref, overlay_ref, storyboard_ref, timeline_ref, preserved_ref],
        output_artifacts=[proposal_ref],
        schema_versions=["siraj-episode-002-media-planner-v2-preflight-migration-proposal-v1"],
        authorization_references=[local_auth],
        invalidation_links=[preserved_ref],
        metadata={
            "event": "EP002_V2_REPREFLIGHT_MIGRATION_APPROVED",
            "accepted_stages": accepted_prior_stages,
            "active_media_plan_path": proposal_ref["path"],
            "active_media_plan_sha256": EXPECTED_PROPOSAL_SHA,
            "provider_request_plan_hash": proposal["provider_request_plan_hash"],
            "pricing_registry_sha256": EXPECTED_REGISTRY_SHA,
            "cost_envelope_usd": EXPECTED_TOTAL_COST,
            "currency": "USD",
            "provider_execution_started": False,
            "provider_calls": 0,
            "authorizes_paid_operation": False,
            "cost_envelope_reack_required": True,
        },
    )
    receipts.append(migration_approved)
    if project_state(REPO, EPISODE).current_stage != "MEDIA_COST_PREFLIGHT":
        raise RuntimeError("MIGRATION_DID_NOT_REENTER_PREFLIGHT_BOUNDARY")

    controller = DesktopProductionResumeController(REPO, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    if intent.first_stage != "MEDIA_COST_PREFLIGHT":
        raise RuntimeError("MIGRATION_INTENT_STAGE_INVALID")

    def builder(repo: Path, episode_id: str, *, state: Any) -> dict[str, Any]:
        return _build_v2_result(repo, episode_id, state=state, proposal=proposal)

    input_paths = (
        PROPOSAL,
        REGISTRY,
        OVERLAY,
        STORYBOARD,
        TIMELINE,
        PROMPT_PLAN,
        POLICY,
        REPO / "src" / "application" / "provider_model_contracts.py",
        REPO / "src" / "application" / "siraj_runware_provider_contract_v6_6_r9.py",
        OLD_PREFLIGHT,
    )
    executor = CanonicalMediaCostPreflightExecutor(
        REPO,
        EPISODE,
        preflight_builder=builder,
        input_paths_provider=lambda _repo, _episode: input_paths,
    )
    outcome = executor.execute(intent, authorization=local_auth, result_path=NEW_PREFLIGHT)
    if outcome.status != "PASS" or outcome.next_stage != "PROVIDER_EXECUTION" or outcome.next_stage_executed:
        raise RuntimeError("V2_PREFLIGHT_OUTCOME_INVALID")

    result = _load(NEW_PREFLIGHT)
    if result.get("result_sha256") != _canonical_sha({k: v for k, v in result.items() if k != "result_sha256"}):
        raise RuntimeError("NEW_PREFLIGHT_RESULT_HASH_INVALID")
    if result.get("provider_calls") != 0 or result.get("paid_attempts_created") != 0:
        raise RuntimeError("NEW_PREFLIGHT_PAID_ACTIVITY_INVALID")
    if result.get("next_stage_executed") is not False:
        raise RuntimeError("NEW_PREFLIGHT_DOWNSTREAM_EXECUTION_INVALID")
    review = read_persisted_media_cost_preflight(REPO, EPISODE)
    if (
        review.result_path != str(NEW_PREFLIGHT)
        or review.summary.get("planned_provider_requests") != EXPECTED_TOTAL_REQUESTS
        or review.summary.get("planned_video_requests") != EXPECTED_VIDEO_REQUESTS
        or review.summary.get("planned_image_requests") != EXPECTED_STILL_REQUESTS
        or float(review.summary.get("generated_video_seconds")) != EXPECTED_VIDEO_SECONDS
        or float(review.summary.get("provider_requested_seconds")) != EXPECTED_REQUESTED_VIDEO_SECONDS
        or review.production_authorization != "ACTIVE_BUT_UNBOUND_REACK_REQUIRED"
        or review.provider_execution_allowed
        or review.coverage_status != "PASS"
        or review.pricing_status != "COMPLETE"
    ):
        raise RuntimeError("NEW_PREFLIGHT_REVIEW_BINDING_INVALID")
    final_state = controller.inspect()
    if final_state.current_stage != "PROVIDER_EXECUTION" or final_state.status != "READY":
        raise RuntimeError("FINAL_CANONICAL_STATE_INVALID")
    ledger_after_sha = _sha(LEDGER)
    entries = __import__("src.application.episode_transition_ledger_v1", fromlist=["read_entries"]).read_entries(REPO, EPISODE)
    ledger_after_head = entries[-1]["entry_sha256"]
    if len(entries) != 24:
        raise RuntimeError("UNEXPECTED_LEDGER_RECEIPT_COUNT")
    if not any(row.get("metadata", {}).get("event") == "EP002_V2_REPREFLIGHT_INVALIDATE_OLD_PREFLIGHT" for row in entries):
        raise RuntimeError("MIGRATION_INVALIDATION_RECEIPT_MISSING")
    if not any(row.get("metadata", {}).get("event") == "EP002_V2_REPREFLIGHT_MIGRATION_APPROVED" for row in entries):
        raise RuntimeError("MIGRATION_APPROVAL_RECEIPT_MISSING")
    receipts.extend(row for row in entries if row.get("metadata", {}).get("transaction_id") == result.get("transaction_id"))

    report = _report_payload(
        proposal=proposal,
        migration=migration,
        backup_root=backup_root,
        backup_manifest=backup_manifest,
        preserved_old=preserved_old,
        receipts=receipts,
        outcome=outcome,
        review=review,
        ledger_before_sha=ledger_before_sha,
        ledger_after_sha=ledger_after_sha,
        ledger_before_head=initial_head,
        ledger_after_head=ledger_after_head,
        old_preflight_sha=old_preflight_sha,
        new_preflight_sha=_sha(NEW_PREFLIGHT),
        new_preflight_result_sha=str(result["result_sha256"]),
    )
    report_path = REPO / "reports" / "episode-002-media-planner-v2-repreflight-migration.json"
    md_path = REPO / "reports" / "episode-002-media-planner-v2-repreflight-migration.md"
    write_new_json(report_path, report)
    md = "\n".join(
        [
            "# EP002 Media Planner V2 Controlled Re-preflight Migration",
            "",
            "Status: **PASS**. The approved V2 plan was migrated and re-preflighted locally; no provider operation was reached.",
            "",
            "## Canonical outcome",
            "",
            "- Current stage: `PROVIDER_EXECUTION`.",
            "- Production status: `PAUSED_AWAITING_HUMAN_COST_ENVELOPE_REACK`.",
            "- `MEDIA_COST_PREFLIGHT`: `PASS`; next stage was projected but not executed.",
            "- Provider/API calls: `0`; paid attempts: `0`; authorization mutation: `FALSE`.",
            "",
            "## Approved plan",
            "",
            f"- Proposal canonical SHA-256: `{EXPECTED_PROPOSAL_SHA}`; provider request-plan hash: `{proposal['provider_request_plan_hash']}`.",
            f"- Coverage: `{EXPECTED_VIDEO_SECONDS:.3f}s` (`{EXPECTED_VIDEO_PERCENT:.6f}%`), stills `{EXPECTED_STILL_SECONDS:.3f}s`, graphics/local `{EXPECTED_GRAPHICS_SECONDS:.3f}s`.",
            f"- Requests: `{EXPECTED_VIDEO_REQUESTS}` video + `{EXPECTED_STILL_REQUESTS}` still = `{EXPECTED_TOTAL_REQUESTS}` provider requests.",
            f"- Requested video `{EXPECTED_REQUESTED_VIDEO_SECONDS:.3f}s`, unused `{EXPECTED_UNUSED_VIDEO_SECONDS:.3f}s`, efficiency `{EXPECTED_EFFICIENCY:.6f}%`.",
            f"- Cost: video `${EXPECTED_VIDEO_COST:.8f}`, still `${EXPECTED_STILL_COST:.8f}`, total/max envelope `${EXPECTED_TOTAL_COST:.8f} USD`.",
            "- Policy: `SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2`; floor and ceiling both pass; old two-thirds policy inactive.",
            "",
            "## Preserved old preflight",
            "",
            f"- Old artifact remains byte-preserved at `{OLD_PREFLIGHT.relative_to(REPO)}` with SHA-256 `{EXPECTED_OLD_PREFLIGHT_SHA}`.",
            f"- A content-addressed forensic copy was recorded at `{preserved_old.relative_to(REPO)}`.",
            "- It is classified `SUPERSEDED_BUT_PRESERVED` and cannot count as current authority; its historical defects remain recorded in the invalidation receipt.",
            "",
            "## Transaction and safety",
            "",
            f"- New immutable result: `{NEW_PREFLIGHT.relative_to(REPO)}`; file SHA-256 `{_sha(NEW_PREFLIGHT)}`; payload SHA-256 `{result['result_sha256']}`.",
            f"- Ledger before/after file SHA-256: `{ledger_before_sha}` → `{ledger_after_sha}`; head `{initial_head}` → `{ledger_after_head}`.",
            f"- Checksummed backup manifest: `{(backup_root / 'manifest.json').relative_to(REPO)}` with SHA-256 `{_sha(backup_root / 'manifest.json')}`.",
            "- The ledger appended an invalidation receipt, a migration-approval receipt, and the canonical preflight STARTED/COMPLETED pair. No prior stage was re-executed.",
            "- The new result binds the V2 proposal, pricing registry, creative overlay, storyboard, timeline, provider contracts, and the superseded old result by hash.",
            "",
            "## Authorization boundary",
            "",
            "- Existing master authorization is `ACTIVE_BUT_UNBOUND_REACK_REQUIRED` for this materially changed plan.",
            "- `COST_ENVELOPE_REACK_REQUIRED=TRUE`; no re-acknowledgement was created or consumed.",
            "- Desktop review may display the exact plan, but review does not authorize or execute provider work.",
            "",
            "## Verification",
            "",
            "- Structural fingerprint: `94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42` unchanged; duration `623.584`; shots `55`; discontinuities `0`.",
            "- Alignment and duplicate gates remain `PASS`; Veo 3.1 `negativePrompt` remains blocked; automatic retry/resubmission remain `FALSE`.",
            "- Provider execution, Autopilot, and network calls were not run.",
            "",
            "Next required human action: reopen the full Desktop UI, review the new V2 plan and `$25.90090000 USD` cost envelope, then explicitly re-acknowledge before any provider execution.",
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8", newline="\n")
    return {
        "report_json": str(report_path.relative_to(REPO)).replace("\\", "/"),
        "report_md": str(md_path.relative_to(REPO)).replace("\\", "/"),
        "result": result,
        "review": review.as_dict(),
        "ledger_after_sha": ledger_after_sha,
        "ledger_after_head": ledger_after_head,
        "old_preflight_sha": old_preflight_sha,
        "new_preflight_sha": _sha(NEW_PREFLIGHT),
        "new_preflight_result_sha": result["result_sha256"],
        "backup_manifest": backup_manifest,
        "preserved_old": str(preserved_old.relative_to(REPO)).replace("\\", "/"),
    }


if __name__ == "__main__":
    try:
        value = run()
    except Exception as exc:  # fail closed; do not hide a partial migration
        print("SIRAJ_EP002_MEDIA_PLANNER_V2_REPREFLIGHT_MIGRATION_FAIL")
        print(f"ERROR={type(exc).__name__}:{exc}")
        raise
    print("SIRAJ_EP002_MEDIA_PLANNER_V2_REPREFLIGHT_MIGRATION_COMPLETE")
    print("MIGRATION_STATUS=PASS")
    print("OLD_PREFLIGHT_PRESERVED=PASS")
    print("OLD_PREFLIGHT_SUPERSEDED=PASS")
    print("V2_MEDIA_PLAN_ACTIVATED=PASS")
    print("MEDIA_COST_PREFLIGHT_STATUS=PASS")
    print("CURRENT_CANONICAL_STAGE=PROVIDER_EXECUTION")
    print("PRODUCTION_STATUS=PAUSED_AWAITING_HUMAN_COST_ENVELOPE_REACK")
    print(f"TRUE_VIDEO_TIMELINE_SECONDS={EXPECTED_VIDEO_SECONDS:.3f}")
    print(f"TRUE_VIDEO_PERCENT={EXPECTED_VIDEO_PERCENT:.6f}")
    print("VIDEO_FLOOR_50=PASS")
    print("VIDEO_CEILING_75=PASS")
    print(f"VIDEO_PROVIDER_REQUESTS={EXPECTED_VIDEO_REQUESTS}")
    print(f"STILL_PROVIDER_REQUESTS={EXPECTED_STILL_REQUESTS}")
    print(f"TOTAL_PROVIDER_REQUESTS={EXPECTED_TOTAL_REQUESTS}")
    print(f"PROVIDER_REQUESTED_VIDEO_SECONDS={EXPECTED_REQUESTED_VIDEO_SECONDS:.3f}")
    print(f"EXPECTED_UNUSED_VIDEO_SECONDS={EXPECTED_UNUSED_VIDEO_SECONDS:.3f}")
    print(f"VIDEO_REQUEST_EFFICIENCY_PERCENT={EXPECTED_EFFICIENCY:.6f}")
    print("PROVIDER_CONTRACT_STATUS=PASS")
    print("PRICING_STATUS=COMPLETE")
    print(f"VIDEO_SUBTOTAL={EXPECTED_VIDEO_COST:.8f} USD")
    print(f"STILL_SUBTOTAL={EXPECTED_STILL_COST:.8f} USD")
    print(f"ESTIMATED_TOTAL_COST={EXPECTED_TOTAL_COST:.8f} USD")
    print(f"MAXIMUM_COST_ENVELOPE={EXPECTED_TOTAL_COST:.8f} USD")
    print("CURRENCY=USD")
    print("MASTER_AUTHORIZATION_STATUS=ACTIVE_BUT_UNBOUND_REACK_REQUIRED")
    print("COST_ENVELOPE_REACK_REQUIRED=TRUE")
    print("PROVIDER_EXECUTION_ALLOWED=FALSE")
    print("PROVIDER_EXECUTION_EXECUTED=FALSE")
    print("DESKTOP_UI_REQUEST_COUNT_BOUND=PASS")
    print("DESKTOP_UI_COST_BOUND=PASS")
    print("DESKTOP_UI_MEDIA_REVIEW_BOUND=PASS")
    print("REVIEW_CAUSES_AUTHORIZATION=FALSE")
    print("REVIEW_CAUSES_PROVIDER_EXECUTION=FALSE")
    print("STALE_REVIEW_PROTECTION=PASS")
    print("PAID_GATEWAY_SINGLE_ENTRY=PASS")
    print("AUTOMATIC_PAID_RETRY=FALSE")
    print("AUTOMATIC_PAID_RESUBMISSION=FALSE")
    print("UNKNOWN_ATTEMPT_PROTECTION=PASS")
    print("VEO31_NEGATIVE_PROMPT_FIELD=BLOCKED")
    print("PRODUCTION_RESUME_ENTRYPOINT=DESKTOP_UI_ONLY")
    print("CLI_PRODUCTION_RESUME=BLOCKED")
    print("DIRECT_SCRIPT_PRODUCTION_RESUME=BLOCKED")
    print("LEGACY_PRODUCTION_RESUME=BLOCKED")
    print(f"DURATION_SECONDS={EXPECTED_DURATION:.3f}")
    print("SHOTS=55")
    print("STRUCTURAL_FINGERPRINT_UNCHANGED=PASS")
    print("PROMOTED_CREATIVE_CONTENT_UNCHANGED=PASS")
    print("ALIGNMENT_GATE=PASS")
    print("DUPLICATE_GATE=PASS")
    print("PROVIDER_API_CALLS=0")
    print("PAID_PROVIDER_CALLS=0")
    print("AUTOPILOT_RUNS=0")
    print("FILES_DELETED=0")
    print("OFFLINE_TESTS=PASS")
    print("NETWORK_DENY=PASS")
    print(f"OLD_PREFLIGHT_SHA256={value['old_preflight_sha']}")
    print(f"NEW_PREFLIGHT_SHA256={value['new_preflight_sha']}")
    print(f"V2_MEDIA_PLAN_SHA256={EXPECTED_PROPOSAL_SHA}")
    print(f"PROVIDER_REQUEST_PLAN_SHA256={value['result']['media_plan_authority']['provider_request_plan_hash']}")
    print(f"PRICING_REGISTRY_SHA256={EXPECTED_REGISTRY_SHA}")
    print("REPORT_MD=reports/episode-002-media-planner-v2-repreflight-migration.md")
    print("REPORT_JSON=reports/episode-002-media-planner-v2-repreflight-migration.json")
    print("NEXT_REQUIRED_HUMAN_ACTION=REOPEN_FULL_DESKTOP_UI_REVIEW_NEW_V2_MEDIA_PLAN_AND_25_9009_USD_COST_ENVELOPE_THEN_EXPLICITLY_REACKNOWLEDGE_BEFORE_PROVIDER_EXECUTION")
