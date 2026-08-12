from __future__ import annotations

import json
from pathlib import Path

from src.application.artifact_provenance_v1 import canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/episode-002-low-utilization-video-review.json"


def load_report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8-sig"))


def test_all_low_units_are_contract_minimum_overhead() -> None:
    report = load_report()
    summary = report["summary"]
    units = report["units"]
    assert len(units) == 18
    assert summary["low_utilization_units_below_75"] == 18
    assert summary["low_utilization_units_below_50"] == 14
    assert summary["low_utilization_units_below_25"] == 8
    assert summary["unavoidable_provider_overhead_units"] == 18
    assert summary["safe_duration_reduction_units"] == 0
    assert summary["safe_merge_units"] == 0
    assert summary["safe_recomposition_units"] == 0
    assert summary["human_review_units"] == 0
    assert all(unit["classification"] == "UNAVOIDABLE_PROVIDER_DURATION_OVERHEAD" for unit in units)
    assert all(unit["smaller_duration_check"]["status"] == "PASS" for unit in units)
    assert all(unit["smaller_duration_check"]["selected_is_smallest_feasible"] for unit in units)


def test_approved_coverage_and_cost_are_unchanged() -> None:
    report = load_report()
    assert report["authority"]["true_video_timeline_seconds"] == 428.56
    assert report["authority"]["true_video_percent"] == 68.725304
    assert report["optimization"]["available"] is False
    assert report["optimization"]["proposed_provider_requested_seconds"] is None
    assert report["optimization"]["proposed_total_cost_usd"] is None
    assert report["optimization"]["cinematic_quality_regression"] is False
    assert report["optimization"]["creative_information_lost"] is False
    assert report["optimization"]["structural_change"] == "NONE"


def test_below_25_units_have_specific_evidence_and_no_reuse() -> None:
    report = load_report()
    below_25 = [unit for unit in report["units"] if unit["utilization_percent"] < 25]
    assert len(below_25) == 8
    assert all(unit["below_25_specific_reason"] for unit in below_25)
    assert all(unit["loop_or_reuse"] is False for unit in report["units"])


def test_report_hash_is_self_consistent_and_migration_not_applied() -> None:
    report = load_report()
    expected = report["report_sha256"]
    payload = dict(report)
    payload.pop("report_sha256")
    assert expected == canonical_sha256(payload)
    assert report["migration_decision"] == "MIGRATE_CURRENT_PLAN"
    assert report["safety"]["migration_applied"] is False
    assert report["safety"]["episode_ledger_mutated"] is False
    assert report["safety"]["provider_api_calls"] == 0
    assert report["safety"]["paid_provider_calls"] == 0
