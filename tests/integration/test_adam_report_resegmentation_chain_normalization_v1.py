from __future__ import annotations

import json
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def test_adam_report_resegmentation_chain_normalization_v1() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    root = (
        project
        / "sources"
        / "secondary"
        / "report-resegmentation-chain-normalization"
    )
    manifest = json.loads(
        (
            root
            / "report-resegmentation-chain-normalization-manifest-v1.json"
        ).read_text(encoding="utf-8-sig")
    )

    assert manifest["status"] == (
        "PASS_NORMALIZED_REPORTS_READY_FOR_BOUNDED_SEMANTIC_REVIEW"
    )
    assert manifest["source_retained_candidate_count"] == 732
    assert manifest["source_single_candidate_count"] == 260
    assert manifest["source_resegmentation_candidate_count"] == 435
    assert manifest["source_merge_candidate_count"] == 37
    assert manifest["consumed_source_candidate_count"] == 732
    assert manifest["normalized_report_count"] > 0
    assert manifest["merge_component_count"] > 0
    assert (
        manifest["permissions"]["gemini_execution_enabled"]
        is False
    )
    assert manifest["permissions"]["hadith_grading_changed"] is False
    assert manifest["permissions"]["narrator_judgement_changed"] is False
    assert (
        manifest["permissions"]["israiliyyat_classification_changed"]
        is False
    )
    assert manifest["next_gate"] == (
        "BOUNDED_GEMINI_SEMANTIC_ANALYSIS_DRAFT"
    )
    assert (
        manifest["next_gate_constraints"]["execution_enabled"]
        is False
    )

    registry_path = (
        project
        / manifest["outputs"]["normalized_report_register"]["project_path"]
    )
    rows = list(iter_jsonl(registry_path))
    assert len(rows) == manifest["normalized_report_count"]

    covered = set()
    for row in rows:
        covered.update(row["retained_parent_report_candidate_ids"])
        assert row["permissions"]["candidate_only"] is True
        assert row["permissions"]["allowed_for_gemini"] is False
        assert row["permissions"]["approved_for_hadith_grade"] is False
        assert row["full_isnad_internal_retention"] is True
        assert row["full_isnad_in_script"] is False
        assert row["review"]["hadith_grading_status"] == "NOT_GRADED"
        assert row["review"]["narrator_identity_status"] == "NOT_RESOLVED"

    assert len(covered) == 732

    chain_path = (
        project
        / manifest["outputs"]["normalized_isnad_chain_candidates"]["project_path"]
    )
    chains = list(iter_jsonl(chain_path))
    assert len(chains) == manifest["normalized_chain_candidate_count"]
    for chain in chains:
        assert chain["full_isnad_internal_retention"] is True
        assert chain["full_isnad_in_script"] is False
        assert chain["hadith_grading_status"] == "NOT_GRADED"
        assert chain["dorar_net_permitted_for_grading"] is False
