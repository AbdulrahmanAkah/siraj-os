from pathlib import Path

from src.application.local_semantic_intelligence.critical_20 import (
    CASES,
    ROUTES,
    adjudicate,
    prepare,
    run_adversarial,
    run_offline,
)


def test_manifest_has_exact_scope(tmp_path: Path) -> None:
    manifest = prepare(tmp_path)
    assert manifest["case_count"] == 20
    assert manifest["legacy_case_count"] == 4
    assert manifest["new_case_count"] == 16
    assert manifest["route_counts"] == {route: 5 for route in ROUTES}
    assert len({item["case_id"] for item in CASES}) == 20


def test_offline_matrix_passes_all_20(tmp_path: Path) -> None:
    report = run_offline(tmp_path)
    assert report["status"] == "PASS"
    assert report["status_counts"] == {"PASS": 20, "PARTIAL": 0, "FAIL": 0}


def test_adversarial_matrix_rejects_all_20(tmp_path: Path) -> None:
    report = run_adversarial(tmp_path)
    assert report["status"] == "PASS"
    assert all(item["status"] == "PASS" for item in report["cases"])


def test_adjudication_requires_real_gemini_run(tmp_path: Path) -> None:
    run_offline(tmp_path)
    report = adjudicate(tmp_path)
    assert report["status"] == "REVIEW_REQUIRED"
    assert all(item["gemini_status"] == "NOT_RUN" for item in report["cases"])
