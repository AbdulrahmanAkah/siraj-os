from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.application.final_review_publish_package_v1 import (
    DEPENDENCY_GRAPH_REL,
    EPISODE_DEFINITION_REL,
    FINAL_MASTER_REL,
    FINAL_RECEIPT_REL,
    ORCHESTRATOR_STATE_REL,
    PUBLISH_MANIFEST_REL,
    QA_REPORT_REL,
    REQUIRED_CHECKLIST_KEYS,
    STAGE_LEDGER_REL,
    FinalReviewError,
    approve_final_review_and_build_publish_package,
    load_final_review_status,
    request_final_review_changes,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    repo = tmp_path / "repo"
    episode_id = "episode-002-test"
    episode = repo / "projects" / episode_id
    final = episode / FINAL_MASTER_REL
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"final-video-bytes")
    write_json(
        episode / FINAL_RECEIPT_REL,
        {
            "status": "COMPLETE_READY_FOR_AUTOMATIC_QA",
            "final_master_sha256": sha256(final),
        },
    )
    qa = episode / QA_REPORT_REL
    write_json(
        qa,
        {
            "schema_version": "siraj-automatic-qa-report-v1",
            "status": "PASS",
            "paid_provider_requests": 0,
        },
    )
    write_json(
        repo / ORCHESTRATOR_STATE_REL,
        {
            "current_episode_id": episode_id,
            "status": "AWAITING_HUMAN_FINAL_REVIEW",
            "stage": "HUMAN_FINAL_REVIEW",
            "next_stage": "HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1",
            "automatic_qa_report_sha256": sha256(qa),
        },
    )
    write_json(
        episode / STAGE_LEDGER_REL,
        {
            "stages": [
                {"stage": "HUMAN_FINAL_REVIEW", "status": "AWAITING_HUMAN"},
                {"stage": "READY_TO_PUBLISH", "status": "QUEUED"},
            ]
        },
    )
    write_json(
        episode / DEPENDENCY_GRAPH_REL,
        {
            "nodes": [
                {"node_id": f"{episode_id}:FINAL_RENDER"},
                {"node_id": f"{episode_id}:AUTOMATIC_QA_REPORT"},
            ],
            "edges": [],
        },
    )
    write_json(
        episode / EPISODE_DEFINITION_REL,
        {
            "episode_id": episode_id,
            "working_title_ar": "عنوان الحلقة",
        },
    )
    return repo, episode, episode_id


def checklist(value: bool = True) -> dict[str, bool]:
    return {key: value for key in REQUIRED_CHECKLIST_KEYS}


def test_approval_requires_complete_checklist(tmp_path: Path) -> None:
    repo, _, _ = build_repo(tmp_path)
    values = checklist()
    values["reviewed_audio_and_sync"] = False
    with pytest.raises(FinalReviewError, match="CHECKLIST_INCOMPLETE"):
        approve_final_review_and_build_publish_package(
            repo,
            reviewer="CREATOR",
            checklist=values,
            title="عنوان الحلقة",
        )


def test_approval_builds_manual_publish_package(tmp_path: Path) -> None:
    repo, episode, _ = build_repo(tmp_path)
    result = approve_final_review_and_build_publish_package(
        repo,
        reviewer="CREATOR",
        checklist=checklist(),
        title="عنوان الحلقة",
        description="وصف الحلقة",
        tags=["سراج", "تاريخ"],
        visibility_preference="PRIVATE",
    )
    assert result.status == "READY_TO_PUBLISH"
    manifest = json.loads((episode / PUBLISH_MANIFEST_REL).read_text(encoding="utf-8"))
    assert manifest["manual_youtube_upload"] is True
    assert manifest["automatic_upload"] == "FORBIDDEN"
    assert manifest["youtube_api_requests"] == 0
    assert manifest["provider_requests"] == 0
    state = json.loads((repo / ORCHESTRATOR_STATE_REL).read_text(encoding="utf-8"))
    assert state["status"] == "READY_TO_PUBLISH"
    assert state["next_stage"] == "MANUAL_YOUTUBE_UPLOAD"


def test_approval_rechecks_final_master_hash(tmp_path: Path) -> None:
    repo, episode, _ = build_repo(tmp_path)
    (episode / FINAL_MASTER_REL).write_bytes(b"tampered")
    with pytest.raises(FinalReviewError, match="FINAL_MASTER_HASH_MISMATCH"):
        approve_final_review_and_build_publish_package(
            repo,
            reviewer="CREATOR",
            checklist=checklist(),
            title="عنوان الحلقة",
        )


def test_visual_change_request_requires_qa_rerun(tmp_path: Path) -> None:
    repo, episode, _ = build_repo(tmp_path)
    result = request_final_review_changes(
        repo,
        reviewer="CREATOR",
        categories=["VISUAL"],
        notes="أصلح اللقطة المتجمدة.",
        shot_ids=["SHOT-017"],
    )
    assert result.status == "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED"
    request = json.loads(result.repair_request_path.read_text(encoding="utf-8"))
    assert request["requires_qa_rerun"] is True
    assert request["repair_target_stage"] == "DESKTOP_MEDIA_EXECUTION"
    assert request["provider_requests"] == 0
    with pytest.raises(FinalReviewError, match="QA_RERUN_REQUIRED"):
        approve_final_review_and_build_publish_package(
            repo,
            reviewer="CREATOR",
            checklist=checklist(),
            title="عنوان الحلقة",
        )
    assert not (episode / PUBLISH_MANIFEST_REL).exists()


def test_metadata_only_change_can_be_approved_without_qa_rerun(tmp_path: Path) -> None:
    repo, _, _ = build_repo(tmp_path)
    request_final_review_changes(
        repo,
        reviewer="CREATOR",
        categories=["METADATA"],
        notes="عدّل العنوان فقط.",
    )
    result = approve_final_review_and_build_publish_package(
        repo,
        reviewer="CREATOR",
        checklist=checklist(),
        title="العنوان المعدل",
    )
    assert result.status == "READY_TO_PUBLISH"


def test_status_reports_ready_to_publish(tmp_path: Path) -> None:
    repo, _, _ = build_repo(tmp_path)
    approve_final_review_and_build_publish_package(
        repo,
        reviewer="CREATOR",
        checklist=checklist(),
        title="عنوان الحلقة",
    )
    status = load_final_review_status(repo)
    assert status["ready_to_publish"] is True
    assert status["manual_youtube_upload"] is True
    assert status["youtube_api_requests"] == 0


def test_change_request_after_approval_invalidates_old_package(tmp_path: Path) -> None:
    repo, episode, _ = build_repo(tmp_path)
    approve_final_review_and_build_publish_package(
        repo,
        reviewer="CREATOR",
        checklist=checklist(),
        title="عنوان الحلقة",
    )
    assert (episode / PUBLISH_MANIFEST_REL).is_file()
    request_final_review_changes(
        repo,
        reviewer="CREATOR",
        categories=["METADATA"],
        notes="تعديل العنوان قبل الرفع.",
    )
    assert not (episode / PUBLISH_MANIFEST_REL).exists()
    status = load_final_review_status(repo)
    assert status["ready_to_publish"] is False
    assert status["can_approve"] is True
