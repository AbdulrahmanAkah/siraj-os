from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def test_adam_report_boundary_isnad_review_v1() -> None:
    repo = Path(__file__).resolve().parents[2]
    root = (
        repo
        / "projects"
        / "episode-001-adam"
        / "sources"
        / "secondary"
        / "report-boundary-isnad-review"
    )

    decisions = json.loads(
        (root / "adam-report-boundary-isnad-decisions-v1.json")
        .read_text(encoding="utf-8-sig")
    )

    assert decisions["status"] == (
        "PASS_REPORT_BOUNDARY_AND_ISNAD_REVIEW_COMPLETE"
    )
    assert decisions["source_report_candidate_count"] == 1136
    assert decisions["counts"]["retained"] == 732
    assert decisions["counts"]["excluded"] == 404
    assert decisions["counts"]["retained_as_single_candidate"] == 260
    assert decisions["counts"]["resegmentation_required"] == 435
    assert decisions["counts"]["merge_required"] == 37
    assert decisions["counts"]["retained_internal_isnad_research_records"] == 545
    assert decisions["counts"]["boundary_excluded_records_verified"] == 559
    assert decisions["manual_ambiguous_records_adjudicated"] == 91
    assert len(decisions["records"]) == 1136

    action_counts = Counter(
        record["review_action"] for record in decisions["records"]
    )
    assert action_counts == {
        "EXCLUDE_OUT_OF_SCOPE": 404,
        "RETAIN_AS_REPORT_CANDIDATE": 260,
        "RETAIN_RESEGMENT_REQUIRED": 435,
        "RETAIN_MERGE_WITH_PREVIOUS": 10,
        "RETAIN_MERGE_WITH_NEXT": 27,
    }

    assert all(
        record["full_isnad_in_script"] is False
        for record in decisions["records"]
    )
    assert all(
        record["full_isnad_internal_retention"] is True
        for record in decisions["records"]
    )
    assert all(
        record["permissions"]["allowed_for_gemini"] is False
        for record in decisions["records"]
    )

    retained = list(iter_jsonl(
        root / "adam-retained-report-register-v1.jsonl"
    ))
    excluded = list(iter_jsonl(
        root / "adam-report-exclusions-v1.jsonl"
    ))
    isnad = list(iter_jsonl(
        root / "adam-refined-internal-isnad-research-queue-v2.jsonl"
    ))
    assert len(retained) == 732
    assert len(excluded) == 404
    assert len(isnad) == 545
    assert all(row["hadith_grading_status"] == "NOT_GRADED" for row in isnad)
    assert all(row["full_isnad_in_script"] is False for row in isnad)

    boundary = json.loads(
        (root / "adam-boundary-exclusion-verification-v1.json")
        .read_text(encoding="utf-8-sig")
    )
    assert boundary["status"] == "PASS"
    assert boundary["excluded_record_count"] == 559
    assert boundary["window_count"] == 18
    assert boundary["ordering_violations"] == 0
