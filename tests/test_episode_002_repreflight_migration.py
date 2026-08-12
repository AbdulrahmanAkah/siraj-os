"""Read-only acceptance checks for the committed EP002 V2 re-preflight."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifact_provenance_v1 import canonical_sha256, sha256_file
from src.application.desktop_media_cost_preflight_v1 import read_persisted_media_cost_preflight
from src.application.desktop_resume_readiness_v1 import read_desktop_episode_state
from src.application.episode_transition_ledger_v1 import project_state, read_entries


REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"
ORCH = REPO / "projects" / EPISODE / "orchestration"
OLD_SHA = "926dea2fc77cf25f2cec1726accc318e9d0d0039955a2e5f719dddacf72f7f05"
OVERLAY_SHA = "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
STRUCTURAL = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"


def test_ep002_repreflight_is_v2_authoritative_and_paused() -> None:
    state = read_desktop_episode_state(REPO, EPISODE)
    review = read_persisted_media_cost_preflight(REPO, EPISODE)
    assert state.current_stage == "PROVIDER_EXECUTION"
    assert review.result_path.endswith("media-cost-preflight-v2.json")
    assert review.summary["planned_provider_requests"] == 95
    assert review.summary["planned_video_requests"] == 73
    assert review.summary["planned_image_requests"] == 22
    assert review.summary["planned_local_graphics"] == 4
    assert review.summary["generated_video_seconds"] == 428.56
    assert review.summary["provider_requested_seconds"] == 496.0
    assert review.summary["expected_unused_video_seconds"] == 67.44
    assert review.cost_envelope_usd["upper_bound"] == 25.9009
    assert review.currency == "USD"
    assert review.production_authorization == "ACTIVE_BUT_UNBOUND_REACK_REQUIRED"
    assert review.provider_execution_allowed is False
    assert review.coverage_status == "PASS"
    assert review.pricing_status == "COMPLETE"


def test_old_preflight_is_byte_preserved_and_excluded() -> None:
    old = ORCH / "media-cost-preflight-v1.json"
    preserved = ORCH / "provenance-history-v1" / f"media-cost-preflight-v1.json.{OLD_SHA}.preserved"
    assert sha256_file(old) == OLD_SHA
    assert preserved.is_file()
    assert sha256_file(preserved) == OLD_SHA
    result = json.loads((ORCH / "media-cost-preflight-v2.json").read_text(encoding="utf-8-sig"))
    assert result["superseded_preflight"]["classification"] == "SUPERSEDED_BUT_PRESERVED"
    assert result["superseded_preflight"]["counts_as_current_authority"] is False


def test_repreflight_receipts_are_hash_valid_and_provider_free() -> None:
    entries = read_entries(REPO, EPISODE)
    assert project_state(REPO, EPISODE).current_stage == "PROVIDER_EXECUTION"
    events = [entry.get("metadata", {}).get("event") for entry in entries]
    assert "EP002_V2_REPREFLIGHT_INVALIDATE_OLD_PREFLIGHT" in events
    assert "EP002_V2_REPREFLIGHT_MIGRATION_APPROVED" in events
    transaction = json.loads((ORCH / "media-cost-preflight-v2.json").read_text(encoding="utf-8-sig"))["transaction_id"]
    stage_rows = [
        entry
        for entry in entries
        if entry.get("metadata", {}).get("transaction_id") == transaction
    ]
    assert [entry["status"] for entry in stage_rows] == ["STARTED", "COMPLETED"]
    assert all(entry.get("metadata", {}).get("provider_calls") == 0 for entry in stage_rows)
    assert all(not entry.get("attempt_references") for entry in stage_rows)


def test_repreflight_structural_and_overlay_identity_remain_bound() -> None:
    result = json.loads((ORCH / "media-cost-preflight-v2.json").read_text(encoding="utf-8-sig"))
    assert result["authoritative_state"]["structural_fingerprint"] == STRUCTURAL
    assert result["authoritative_state"]["promoted_overlay_sha256"] == OVERLAY_SHA
    assert result["authoritative_state"]["duration_seconds"] == 623.584
    assert result["authoritative_state"]["shot_count"] == 55
    assert result["authoritative_state"]["timeline_discontinuities"] == 0
    assert result["result_sha256"] == canonical_sha256({k: v for k, v in result.items() if k != "result_sha256"})


def test_desktop_review_and_dashboard_bind_reack_status_without_execution() -> None:
    dashboard = (REPO / "src/presentation/desktop/v6_dashboard_integration.py").read_text(encoding="utf-8")
    dialog = (REPO / "src/presentation/desktop/media_preflight_review_v1.py").read_text(encoding="utf-8")
    assert "COST ENVELOPE RE-ACK REQUIRED" in dashboard
    assert "PAUSED / AWAITING HUMAN COST ENVELOPE RE-ACK" in dashboard
    assert "Request cost-envelope re-acknowledgement" in dialog
    assert "read_persisted_media_cost_preflight" in dashboard
    assert "provider adapter" not in dialog.lower()
