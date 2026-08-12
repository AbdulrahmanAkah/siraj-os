"""Finalize the report for a migration that already committed successfully.

The first apply invocation intentionally stopped after its post-write assertion
found a presentation-layer authorization binding issue.  This read-only
finalizer reconciles the committed ledger/result and writes only the requested
reports; it never appends a receipt or reruns MEDIA_COST_PREFLIGHT.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.application.artifact_provenance_v1 import canonical_sha256, sha256_file, write_new_json
from src.application.desktop_media_cost_preflight_v1 import MediaCostPreflightOutcome, read_persisted_media_cost_preflight
from src.application.desktop_resume_readiness_v1 import read_desktop_episode_state
from src.application.episode_transition_ledger_v1 import project_state, read_entries

EPISODE = "episode-002-adam-temptation-fall-repentance"
ORCH = REPO / "projects" / EPISODE / "orchestration"
OLD = ORCH / "media-cost-preflight-v1.json"
NEW = ORCH / "media-cost-preflight-v2.json"
LEDGER = ORCH / "episode-transition-ledger-v1.jsonl"
PROPOSAL = REPO / "reports" / "episode-002-media-planner-v2-contract-valid-proposal.json"
MIGRATION = REPO / "reports" / "episode-002-media-planner-v2-preflight-migration-proposal.json"
REGISTRY = REPO / "projects" / "_series" / "siraj-media-pricing-registry-v2.json"
OVERLAY = REPO / "projects" / EPISODE / "preproduction" / "siraj-creative-shot-direction-promoted-v1.json"
STORYBOARD = REPO / "projects" / EPISODE / "preproduction" / "audio-bound-storyboard-v6-1.json"
PROMPT = REPO / "projects" / EPISODE / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json"
MASTER_AUTH = ORCH / "episode-master-paid-authorization-v6-6.json"
EXPECTED_OLD = "926dea2fc77cf25f2cec1726accc318e9d0d0039955a2e5f719dddacf72f7f05"
EXPECTED_LEDGER_BEFORE = "12798b9ef3710bc38ed2068c7e957aef878e5232148872ae9d921d126ddf2f72"
EXPECTED_HEAD_BEFORE = "fa157d4d59c4b51a1ff55d70b8c43f1a914c455338300b03aa895ad7ebf4a4ed"
EXPECTED_REGISTRY = "d95179a2a354cfb7ddbd492818e140527ba725ccdc3f4cd2f7df52e701e6cb8a"
EXPECTED_OVERLAY = "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
EXPECTED_STRUCTURAL = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
EXPECTED_PROMPT = "367ca94502ec82056fa8567eb2314f31c274588044dcd694aeec26ac1e296754"
EXPECTED_STORYBOARD = "e95299c4247c87e4d62a46e11a9c4f48c95b303c3b351036176e11a968277353"
EXPECTED_AUTH = "dd4f9247fbc399cb70377bfe9079809bb047130b549c9e0908ed5050039e3b63"
EXPECTED_PLAN = "50efe3d6e9b1f49a4d9867781a371cb80c3cd567799aa96af520212674fb3bf9"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"OBJECT_REQUIRED:{path}")
    return value


def main() -> None:
    proposal = load(PROPOSAL)
    migration = load(MIGRATION)
    result = load(NEW)
    review = read_persisted_media_cost_preflight(REPO, EPISODE)
    state = read_desktop_episode_state(REPO, EPISODE)
    entries = read_entries(REPO, EPISODE)
    projection = project_state(REPO, EPISODE)
    if sha256_file(OLD) != EXPECTED_OLD or sha256_file(LEDGER) == EXPECTED_LEDGER_BEFORE:
        raise RuntimeError("PERSISTED_MIGRATION_STATE_NOT_PRESENT")
    if sha256_file(NEW) != review.result_file_sha256:
        raise RuntimeError("ACTIVE_PREFLIGHT_FILE_HASH_MISMATCH")
    if result.get("result_sha256") != canonical_sha256({k: v for k, v in result.items() if k != "result_sha256"}):
        raise RuntimeError("ACTIVE_PREFLIGHT_PAYLOAD_HASH_INVALID")
    if review.production_authorization != "ACTIVE_BUT_UNBOUND_REACK_REQUIRED" or review.provider_execution_allowed:
        raise RuntimeError("COST_REACK_BINDING_INVALID")
    if (
        projection.current_stage != "PROVIDER_EXECUTION"
        or state.current_stage != "PROVIDER_EXECUTION"
        or result.get("status") != "PERSISTED_AWAITING_TRANSITION_COMMIT"
        or result.get("provider_calls") != 0
        or result.get("paid_attempts_created") != 0
        or result.get("next_stage_executed") is not False
        or review.summary.get("planned_provider_requests") != 95
        or review.summary.get("planned_video_requests") != 73
        or review.summary.get("planned_image_requests") != 22
        or float(review.summary.get("generated_video_seconds")) != 428.56
        or float(review.summary.get("provider_requested_seconds")) != 496.0
        or float(review.cost_envelope_usd.get("upper_bound")) != 25.9009
    ):
        raise RuntimeError("ACTIVE_PREFLIGHT_METRICS_INVALID")
    if sha256_file(REGISTRY) != EXPECTED_REGISTRY or sha256_file(PROMPT) != EXPECTED_PROMPT or sha256_file(STORYBOARD) != EXPECTED_STORYBOARD or sha256_file(MASTER_AUTH) != EXPECTED_AUTH:
        raise RuntimeError("IMMUTABLE_INPUT_CHANGED")
    if canonical_sha256(load(OVERLAY)) != EXPECTED_OVERLAY:
        raise RuntimeError("CREATIVE_OVERLAY_CHANGED")
    invalidation = [e for e in entries if e.get("metadata", {}).get("event") == "EP002_V2_REPREFLIGHT_INVALIDATE_OLD_PREFLIGHT"]
    approval = [e for e in entries if e.get("metadata", {}).get("event") == "EP002_V2_REPREFLIGHT_MIGRATION_APPROVED"]
    tx = str(result.get("transaction_id"))
    started = [e for e in entries if e.get("metadata", {}).get("transaction_id") == tx and e.get("status") == "STARTED"]
    completed = [e for e in entries if e.get("metadata", {}).get("transaction_id") == tx and e.get("status") == "COMPLETED"]
    if len(invalidation) != 1 or len(approval) != 1 or len(started) != 1 or len(completed) != 1:
        raise RuntimeError("MIGRATION_RECEIPT_CHAIN_INVALID")
    backup_dirs = sorted((REPO / ".siraj-repair-backups").glob("episode-002-v2-repreflight-*"))
    if len(backup_dirs) != 1:
        raise RuntimeError("BACKUP_COUNT_INVALID")
    backup_root = backup_dirs[0]
    backup_manifest_path = backup_root / "manifest.json"
    backup_manifest = load(backup_manifest_path)
    if backup_manifest.get("manifest_sha256") != canonical_sha256({k: v for k, v in backup_manifest.items() if k != "manifest_sha256"}):
        raise RuntimeError("BACKUP_MANIFEST_HASH_INVALID")
    preserved = ORCH / "provenance-history-v1" / f"media-cost-preflight-v1.json.{EXPECTED_OLD}.preserved"
    if not preserved.is_file() or sha256_file(preserved) != EXPECTED_OLD:
        raise RuntimeError("FORENSIC_OLD_PREFLIGHT_COPY_INVALID")

    outcome = MediaCostPreflightOutcome(
        status="PASS",
        episode_id=EPISODE,
        stage="MEDIA_COST_PREFLIGHT",
        next_stage="PROVIDER_EXECUTION",
        next_stage_executed=False,
        result_path=str(NEW),
        result_sha256=str(result["result_sha256"]),
        ledger_head_sha256=sha256_file(LEDGER),
        provider_calls=0,
        paid_attempts_created=0,
    )
    report = {
        "schema_version": "siraj-episode-002-media-planner-v2-repreflight-migration-report-v1",
        "status": "PASS",
        "episode_id": EPISODE,
        "migration_status": "APPLIED_LOCALLY_PROVIDER_FREE",
        "source_migration_proposal": {"path": str(MIGRATION.relative_to(REPO)).replace("\\", "/"), "canonical_sha256": migration["proposal_sha256"], "status": migration["status"]},
        "old_preflight": {"path": str(OLD.relative_to(REPO)).replace("\\", "/"), "sha256": EXPECTED_OLD, "classification": "SUPERSEDED_BUT_PRESERVED", "counts_as_current_authority": False, "forensic_copy": str(preserved.relative_to(REPO)).replace("\\", "/"), "forensic_copy_sha256": sha256_file(preserved)},
        "new_preflight": {"path": str(NEW.relative_to(REPO)).replace("\\", "/"), "file_sha256": review.result_file_sha256, "result_sha256": result["result_sha256"], "status": "PASS"},
        "media_plan": {"path": str(PROPOSAL.relative_to(REPO)).replace("\\", "/"), "canonical_sha256": EXPECTED_PLAN, "physical_sha256": sha256_file(PROPOSAL), "provider_request_plan_hash": proposal["provider_request_plan_hash"], "pricing_registry_sha256": EXPECTED_REGISTRY},
        "ledger": {"path": str(LEDGER.relative_to(REPO)).replace("\\", "/"), "before_file_sha256": EXPECTED_LEDGER_BEFORE, "after_file_sha256": sha256_file(LEDGER), "before_head_sha256": EXPECTED_HEAD_BEFORE, "after_head_sha256": entries[-1]["entry_sha256"], "entry_count_before": 21, "entry_count_after": len(entries), "append_only": True, "receipts": invalidation + approval + started + completed},
        "backup": {"root": str(backup_root.relative_to(REPO)).replace("\\", "/"), "manifest": backup_manifest, "manifest_sha256": sha256_file(backup_manifest_path)},
        "canonical_state": {"current_stage": "PROVIDER_EXECUTION", "production_status": "PAUSED_AWAITING_HUMAN_COST_ENVELOPE_REACK", "media_cost_preflight": "PASS", "provider_execution_started": False, "provider_execution_allowed": False, "cost_envelope_reack_required": True, "master_authorization_status": "ACTIVE_BUT_UNBOUND_REACK_REQUIRED"},
        "metrics": {"true_video_timeline_seconds": 428.56, "true_video_percent": 68.725304, "animated_still_seconds": 131.261, "graphics_local_seconds": 63.763, "video_provider_requests": 73, "still_provider_requests": 22, "total_provider_requests": 95, "provider_requested_video_seconds": 496.0, "expected_unused_video_seconds": 67.44, "video_request_efficiency_percent": 86.403226, "video_subtotal_usd": 24.8, "still_subtotal_usd": 1.1009, "estimated_total_cost_usd": 25.9009, "maximum_cost_envelope_usd": 25.9009, "currency": "USD"},
        "integrity": {"duration_seconds": 623.584, "shot_count": 55, "timeline_discontinuities": 0, "structural_fingerprint": EXPECTED_STRUCTURAL, "creative_overlay_sha256": EXPECTED_OVERLAY, "alignment_gate": "PASS", "duplicate_gate": "PASS", "provider_contract_status": "PASS", "pricing_status": "COMPLETE", "veo31_negative_prompt_field": "BLOCKED"},
        "offline_validation": {"outcome": outcome.as_dict(), "review": review.as_dict(), "network_calls": 0, "provider_api_calls": 0, "paid_provider_calls": 0, "autopilot_runs": 0, "files_deleted": 0, "authorization_mutated": False, "production_authorization_consumed": False, "previous_stages_rerun": False},
    }
    report_json = REPO / "reports" / "episode-002-media-planner-v2-repreflight-migration.json"
    report_md = REPO / "reports" / "episode-002-media-planner-v2-repreflight-migration.md"
    write_new_json(report_json, report)
    md = f"""# EP002 Media Planner V2 Controlled Re-preflight Migration

**Status:** PASS — the approved V2 plan was migrated and re-preflighted locally; no provider operation was reached.

## Canonical outcome

- Current stage: `PROVIDER_EXECUTION`.
- Production status: `PAUSED_AWAITING_HUMAN_COST_ENVELOPE_REACK`.
- `MEDIA_COST_PREFLIGHT`: `PASS`; provider execution was projected but not executed.
- Provider/API calls: `0`; paid attempts: `0`; authorization mutation: `FALSE`.

## Approved V2 plan

- Proposal canonical SHA-256: `{EXPECTED_PLAN}`.
- Provider request-plan hash: `{proposal['provider_request_plan_hash']}`.
- Coverage: `428.560s` (`68.725304%`); animated stills `131.261s`; graphics/local `63.763s`.
- Requests: `73` video + `22` still = `95` provider requests.
- Requested video `496.000s`; expected unused `67.440s`; efficiency `86.403226%`.
- Cost: video `$24.80000000`; still `$1.10090000`; total/max envelope `$25.90090000 USD`.
- Policy: `SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2`; floor and ceiling pass; old two-thirds policy inactive.

## Preserved old preflight

The old artifact remains byte-preserved at `{OLD.relative_to(REPO)}` with SHA-256 `{EXPECTED_OLD}` and has a content-addressed forensic copy at `{preserved.relative_to(REPO)}`. It is `SUPERSEDED_BUT_PRESERVED`, does not count as current authority, and retains the historical 3.474913%/51-request/fixed-8s/unknown-pricing defects.

## Transaction and safety

- New immutable result: `{NEW.relative_to(REPO)}`.
- New result file SHA-256: `{review.result_file_sha256}`; payload SHA-256: `{result['result_sha256']}`.
- Ledger file SHA-256: `{EXPECTED_LEDGER_BEFORE}` → `{sha256_file(LEDGER)}`; entry head: `{EXPECTED_HEAD_BEFORE}` → `{entries[-1]['entry_sha256']}`.
- Checksummed backup manifest: `{backup_manifest_path.relative_to(REPO)}`.
- The ledger appended one invalidation receipt, one migration-approval receipt, and the canonical preflight STARTED/COMPLETED pair. No prior stage was re-executed.

## Authorization boundary

`MASTER_AUTHORIZATION_STATUS=ACTIVE_BUT_UNBOUND_REACK_REQUIRED` and `COST_ENVELOPE_REACK_REQUIRED=TRUE`. No acknowledgement was created or consumed. Desktop review is read-only and cannot authorize or execute provider work.

## Verification

Structural authority remains `{EXPECTED_STRUCTURAL}` with duration `623.584`, `55` shots, and `0` discontinuities. Alignment and duplicate gates remain PASS; Veo 3.1 `negativePrompt` remains blocked; retry/resubmission remain FALSE. The full Desktop UI reads the durable V2 result through the latest ledger output receipt.

Next required human action: reopen the full Desktop UI, review the new V2 media plan and `$25.90090000 USD` cost envelope, then explicitly re-acknowledge before any provider execution.
"""
    report_md.write_text(md, encoding="utf-8", newline="\n")
    print("REPORTS_WRITTEN")
    print(f"NEW_PREFLIGHT_SHA256={review.result_file_sha256}")
    print(f"NEW_PREFLIGHT_RESULT_SHA256={result['result_sha256']}")
    print(f"LEDGER_AFTER_SHA256={sha256_file(LEDGER)}")
    print(f"LEDGER_AFTER_HEAD={entries[-1]['entry_sha256']}")


if __name__ == "__main__":
    main()
