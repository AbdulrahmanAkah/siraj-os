from __future__ import annotations

import json
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def test_adam_report_level_extraction_v1() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    root = (
        project
        / "sources"
        / "secondary"
        / "report-level-extraction"
    )

    manifest = json.loads(
        (
            root
            / "report-level-extraction-manifest-v1.json"
        ).read_text(encoding="utf-8-sig")
    )

    assert manifest["status"] == "PASS_REPORT_CANDIDATES_READY"
    assert manifest["included_window_count"] == 92
    assert manifest["source_count"] == 9
    assert manifest["report_candidate_count"] > 92
    decisions_path = (
        project
        / "sources"
        / "secondary"
        / "final-window-review"
        / "adam-human-window-decisions-v1.json"
    )
    decisions = json.loads(
        decisions_path.read_text(encoding="utf-8-sig")
    )
    expected_rebuilt = sum(
        1
        for row in decisions["decisions"]
        if row["decision"] == "INCLUDE"
        and (
            (row.get("repair_review") or {}).get(
                "text_complete_for_candidates"
            )
            is True
        )
    )
    assert expected_rebuilt == 26
    assert (
        manifest["candidate_centered_rebuilt_window_count"]
        == expected_rebuilt
    )
    assert (
        manifest["permissions"]["gemini_execution_enabled"]
        is False
    )
    assert (
        manifest["permissions"]["hadith_grading_changed"]
        is False
    )
    assert (
        manifest["permissions"][
            "israiliyyat_classification_changed"
        ]
        is False
    )
    assert manifest["next_gate"] == (
        "HUMAN_REPORT_BOUNDARY_AND_ISNAD_REVIEW"
    )

    registry_path = (
        project
        / manifest["outputs"][
            "report_candidate_registry"
        ]["project_path"]
    )
    rows = list(iter_jsonl(registry_path))
    assert len(rows) == manifest["report_candidate_count"]

    for row in rows:
        assert row["permissions"]["candidate_only"] is True
        assert row["permissions"]["allowed_for_gemini"] is False
        assert (
            row["permissions"]["approved_for_evidence"]
            is False
        )
        assert (
            row["permissions"]["approved_for_quotation"]
            is False
        )
        assert (
            row["script_attribution_candidate"][
                "full_isnad_in_script"
            ]
            is False
        )

    isnad_path = (
        project
        / manifest["outputs"][
            "internal_isnad_research_queue"
        ]["project_path"]
    )
    isnad_rows = list(iter_jsonl(isnad_path))
    assert len(isnad_rows) == (
        manifest["internal_isnad_research_count"]
    )
    for row in isnad_rows:
        assert row["full_isnad_internal_retention"] is True
        assert row["full_isnad_in_script"] is False
        assert row["hadith_grading_status"] == "NOT_GRADED"
        assert row["dorar_net_permitted_for_grading"] is False

