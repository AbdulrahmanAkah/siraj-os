from __future__ import annotations

import json
from pathlib import Path


def test_adam_human_window_review_workbench_v1() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    root = (
        project
        / "sources"
        / "secondary"
        / "human-window-review"
    )
    manifest = json.loads(
        (root / "human-window-review-manifest-v1.json").read_text(
            encoding="utf-8-sig"
        )
    )

    assert manifest["status"] == "PASS_REVIEW_WORKBENCH_READY"
    assert manifest["source_window_count"] == 207
    assert manifest["shortlist_count"] > 0
    assert manifest["reserve_count"] >= 0
    assert (
        manifest["shortlist_count"] + manifest["reserve_count"]
        == manifest["source_window_count"]
    )
    assert manifest["permissions"]["gemini_execution_enabled"] is False
    assert manifest["permissions"]["source_approval_changed"] is False
    assert manifest["permissions"]["quotation_approval_changed"] is False
    assert manifest["permissions"]["report_classification_changed"] is False
    assert manifest["permissions"]["israiliyyat_classification_changed"] is False

    html_path = root / "adam-human-window-review-workbench-v1.html"
    assert html_path.is_file()
    document = html_path.read_text(encoding="utf-8")
    assert "siraj-adam-window-review-v1" in document
    assert "تصدير القرارات JSON" in document
    assert "allowed_for_gemini" in document
