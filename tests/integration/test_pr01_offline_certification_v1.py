from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = REPO_ROOT / "reports/pr01-production-readiness"


def test_pr01_certificate_is_pass_and_never_authorizes_production() -> None:
    certificate = json.loads(
        (REPORT_ROOT / "SIRAJ_PR01_PRODUCTION_READINESS_CERTIFICATION_V1.json").read_text(encoding="utf-8")
    )
    assert certificate["PR01_STATUS"] == "PR01_PRODUCTION_READINESS_PASS"
    assert certificate["PRODUCTION_AUTHORIZED"] is False
    assert certificate["PAID_EXECUTION_AUTHORIZED"] is False
    assert certificate["EXECUTION_COUNTS"]["provider_calls"] == 0
    assert certificate["EXECUTION_COUNTS"]["paid_calls"] == 0
    assert certificate["CRITICAL_OR_HIGH_UNRESOLVED"] == 0


def test_r27_manifest_is_inventory_only_and_exactly_27_units() -> None:
    handoff = json.loads(
        (REPORT_ROOT / "EP002_R27_REVIEW_INPUT_MANIFEST_V1.json").read_text(encoding="utf-8")
    )
    assert handoff["status"] == "PASS"
    assert handoff["inventory_only"] is True
    assert handoff["actual_asset_review_performed"] is False
    assert handoff["actual_unit_count"] == 27
    assert handoff["human_review_decisions"] == 0
    assert handoff["montage_allowed"] is False
    assert handoff["qa_allowed"] is False
    assert all(row["review_decision"] == "NOT_STARTED" for row in handoff["units"])
