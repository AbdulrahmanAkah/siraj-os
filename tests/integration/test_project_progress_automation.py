from __future__ import annotations

import json
from pathlib import Path

from scripts.project_progress.recorder import (
    AUTO_BEGIN,
    AUTO_END,
    record_milestone,
)


def test_record_milestone_is_idempotent(
    tmp_path: Path,
) -> None:
    progress = tmp_path / "PROJECT_PROGRESS.md"
    ledger = tmp_path / "milestones.json"

    progress.write_text(
        "# SIRAJ OS\n## Master Development Roadmap\n",
        encoding="utf-8",
    )

    arguments = {
        "project_progress_path": progress,
        "ledger_path": ledger,
        "milestone_id": "milestone-1",
        "title_ar": "اختبار",
        "status": "COMPLETED",
        "summary_ar": "ملخص",
        "next_action_ar": "الخطوة التالية",
        "recorded_at": "2026-07-21T00:00:00+00:00",
    }

    record_milestone(**arguments)
    record_milestone(
        **{
            **arguments,
            "summary_ar": "ملخص محدث",
        }
    )

    payload = json.loads(
        ledger.read_text(encoding="utf-8")
    )

    assert len(payload["milestones"]) == 1
    assert (
        payload["milestones"][0]["summary_ar"]
        == "ملخص محدث"
    )

    document = progress.read_text(
        encoding="utf-8"
    )

    assert document.count(AUTO_BEGIN) == 1
    assert document.count(AUTO_END) == 1


def test_project_progress_contains_real_video_milestone() -> None:
    repo = Path(__file__).resolve().parents[2]

    ledger_path = (
        repo
        / "docs"
        / "execution"
        / "project-milestones.json"
    )

    payload = json.loads(
        ledger_path.read_text(encoding="utf-8")
    )

    milestones = {
        item["milestone_id"]: item
        for item in payload["milestones"]
    }

    assert (
        "2026-07-21-media-video-prototype"
        in milestones
    )

    assert (
        milestones[
            "2026-07-21-media-video-prototype"
        ]["status"]
        == "COMPLETED_WITH_LIMITATIONS"
    )


def test_media_readiness_is_not_reported_as_zero() -> None:
    repo = Path(__file__).resolve().parents[2]

    report = json.loads(
        (
            repo
            / "artifacts"
            / "fast-track"
            / "pipeline-readiness.json"
        ).read_text(encoding="utf-8")
    )

    assert (
        report["stage_status"]["media_execution"]
        == "PROTOTYPE_WORKING"
    )

    assert (
        report["stage_status"][
            "publishable_media_execution"
        ]
        == "BLOCKED"
    )
