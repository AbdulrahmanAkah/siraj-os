from __future__ import annotations

import csv
import json
from pathlib import Path


def test_adam_bounded_gemini_semantic_draft_v1() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    root = (
        project
        / "sources"
        / "secondary"
        / "gemini-semantic-analysis-draft"
    )
    manifest = json.loads(
        (
            root
            / "gemini-semantic-analysis-draft-manifest-v1.json"
        ).read_text(encoding="utf-8-sig")
    )
    lock = json.loads(
        (root / "execution-lock-v1.json").read_text(
            encoding="utf-8-sig"
        )
    )

    assert manifest["status"] == (
        "PASS_GEMINI_DRAFTS_READY_EXECUTION_BLOCKED"
    )
    assert manifest["normalized_report_count"] == 738
    assert manifest["unresolved_boundary_count"] == 446
    assert manifest["stable_report_count"] == 292
    assert manifest["normalized_chain_candidate_count"] == 448

    assert manifest["task_counts"] == {
        "boundary_resolution_records": 446,
        "stable_semantic_mapping_records": 292,
        "chain_interpretation_records": 448,
        "chain_records_depending_on_boundary_resolution": (
            manifest["task_counts"][
                "chain_records_depending_on_boundary_resolution"
            ]
        ),
    }
    assert (
        0
        <= manifest["task_counts"][
            "chain_records_depending_on_boundary_resolution"
        ]
        <= 448
    )

    assert manifest["batch_counts"]["total_batches"] > 0
    assert manifest["permissions"]["gemini_execution_enabled"] is False
    assert manifest["permissions"]["network_call_made"] is False
    assert manifest["permissions"]["hadith_grading_changed"] is False
    assert manifest["permissions"]["narrator_judgement_changed"] is False
    assert manifest["permissions"]["isnad_approval_changed"] is False
    assert (
        manifest["permissions"]["israiliyyat_classification_changed"]
        is False
    )
    assert manifest["next_gate"] == (
        "EXPLICIT_GEMINI_EXECUTION_AUTHORIZATION"
    )

    assert lock["execution_enabled"] is False
    assert lock["network_call_present_in_this_phase"] is False
    assert lock["explicit_user_authorization_required"] is True

    batch_index = root / "batch-index-v1.csv"
    with batch_index.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == manifest["batch_counts"]["total_batches"]
    for row in rows:
        assert row["execution_status"] == "BLOCKED_NOT_AUTHORIZED"
        path = project / row["project_path"]
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        assert payload["execution_enabled"] is False
        assert payload["execution_status"] == "BLOCKED_NOT_AUTHORIZED"
        assert payload["provider_id"] == "GEMINI"
        assert payload["model_id"] is None
        assert 1 <= payload["record_count"] <= (
            manifest["configuration"]["maximum_records_per_batch"]
        )
