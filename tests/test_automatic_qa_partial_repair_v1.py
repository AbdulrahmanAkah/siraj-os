from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.application.automatic_qa_partial_repair_v1 as qa
from src.application.automatic_qa_partial_repair_v1 import (
    AutomaticQAResult,
    QAIssue,
    QAEnvironment,
    evaluate_automatic_qa,
    load_automatic_qa_status,
    run_automatic_qa_and_partial_repair,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _environment(tmp_path: Path) -> QAEnvironment:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"x")
    ffprobe.write_bytes(b"x")
    return QAEnvironment(
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        ffmpeg_version_line="ffmpeg test",
        available_filters=qa.REQUIRED_QA_FILTERS,
        missing_filters=(),
    )


def _prepare(tmp_path: Path) -> tuple[str, Path]:
    episode_id = "episode-002-qa-test"
    root = tmp_path / "projects" / episode_id
    _write(
        tmp_path / qa.ORCHESTRATOR_STATE_REL,
        {
            "current_episode_id": episode_id,
            "status": "FINAL_RENDER_READY_FOR_QA",
            "stage": "AUTOMATIC_QA",
        },
    )
    shots = []
    for index in range(1, 71):
        shot_id = f"SH-{index:03d}"
        source = root / "sources" / f"{shot_id}.bin"
        output = root / qa.SHOT_DIR_REL / f"{shot_id}.mp4"
        receipt = root / qa.SHOT_RECEIPT_DIR_REL / f"{shot_id}-receipt.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(("source-" + shot_id).encode())
        output.write_bytes(("output-" + shot_id).encode())
        source_hash = qa._sha256(source)
        output_hash = qa._sha256(output)
        fingerprint = f"fp-{index}"
        _write(
            receipt,
            {
                "status": "COMPLETE",
                "source_sha256": source_hash,
                "output_sha256": output_hash,
                "render_fingerprint_sha256": fingerprint,
            },
        )
        shots.append(
            {
                "shot_id": shot_id,
                "queue_index": index,
                "treatment": (
                    "ANIMATED_STILL_COMPOSITING"
                    if index <= 44
                    else "GENERATED_VIDEO"
                    if index <= 64
                    else "GRAPHICS"
                ),
                "duration_seconds": 18.0,
                "source_duration_seconds": None if index <= 44 else 8.0,
                "source_path_relative": str(source.relative_to(tmp_path)).replace("\\", "/"),
                "source_sha256": source_hash,
                "output_path_relative": str(output.relative_to(tmp_path)).replace("\\", "/"),
                "receipt_path_relative": str(receipt.relative_to(tmp_path)).replace("\\", "/"),
                "render_fingerprint_sha256": fingerprint,
            }
        )
    _write(
        root / qa.RENDER_PLAN_REL,
        {
            "episode_id": episode_id,
            "music": "FORBIDDEN",
            "flat_slideshow": "FORBIDDEN",
            "episode_duration_seconds": 1260.0,
            "shots": shots,
        },
    )
    audio = root / qa.AUDIO_MASTER_REL
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"audio")
    final = root / qa.FINAL_MASTER_REL
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"final")
    _write(
        root / qa.FINAL_RECEIPT_REL,
        {
            "final_master_sha256": qa._sha256(final),
            "audio_master_sha256": qa._sha256(audio),
        },
    )
    _write(
        root / qa.STAGE_LEDGER_REL,
        {
            "stages": [
                {"stage": "STRUCTURAL_MONTAGE", "status": "COMPLETE"},
                {"stage": "AUTOMATIC_QA", "status": "QUEUED"},
                {"stage": "HUMAN_FINAL_REVIEW", "status": "QUEUED"},
            ]
        },
    )
    return episode_id, root


def _pass_evaluation(episode_id: str) -> dict:
    return {
        "schema_version": "siraj-automatic-qa-evaluation-v1",
        "release": qa.RELEASE,
        "episode_id": episode_id,
        "status": "PASS",
        "quality_score": 100,
        "blocking_issue_count": 0,
        "warning_count": 0,
        "issues": [],
        "repair_plan": {
            "local_shot_ids": [],
            "local_final_remux": False,
            "upstream_media_shot_ids": [],
            "upstream_audio_required": False,
            "manual_blocking_review_required": False,
            "paid_provider_requests_authorized": 0,
        },
    }


def test_video_profile_contract() -> None:
    valid = {
        "format": {"duration": "10.0", "bit_rate": "5000000"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
                "pix_fmt": "yuv420p",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "bit_rate": "192000",
            },
        ],
    }
    assert qa._video_profile_issues(
        valid,
        scope="FINAL_MASTER",
        shot_id=None,
        expected_duration=10.0,
        require_audio=True,
    ) == []
    invalid = json.loads(json.dumps(valid))
    invalid["streams"][0]["width"] = 1280
    issues = qa._video_profile_issues(
        invalid,
        scope="FINAL_MASTER",
        shot_id=None,
        expected_duration=10.0,
        require_audio=True,
    )
    assert any(issue.code == "FINAL_VIDEO_PROFILE_INVALID" for issue in issues)


def test_evaluation_builds_local_and_upstream_repair_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_id, _ = _prepare(tmp_path)
    calls = 0

    def fake_shot(repo, env, shot):
        nonlocal calls
        calls += 1
        if shot["shot_id"] == "SH-001":
            return [
                QAIssue(
                    code="SHOT_OUTPUT_HASH_MISMATCH",
                    severity="BLOCKING",
                    scope="SHOT",
                    detail="hash",
                    repair_class="LOCAL_SHOT_RERENDER",
                    shot_id="SH-001",
                )
            ], {"shot_id": "SH-001", "status": "BLOCKED"}
        if shot["shot_id"] == "SH-045":
            return [
                QAIssue(
                    code="GENERATED_SOURCE_VISUAL_DEFECT",
                    severity="BLOCKING",
                    scope="SHOT",
                    detail="freeze",
                    repair_class="UPSTREAM_MEDIA_REQUIRED",
                    shot_id="SH-045",
                )
            ], {"shot_id": "SH-045", "status": "BLOCKED"}
        return [], {"shot_id": shot["shot_id"], "status": "PASS"}

    monkeypatch.setattr(qa, "_check_shot", fake_shot)
    monkeypatch.setattr(qa, "_check_final", lambda *args: ([], {}))
    monkeypatch.setattr(qa, "_sha256", lambda path: str(path))
    evaluation = evaluate_automatic_qa(
        tmp_path,
        environment=_environment(tmp_path),
    )
    assert calls == 70
    assert evaluation["status"] == "BLOCKED"
    assert evaluation["repair_plan"]["local_shot_ids"] == ["SH-001"]
    assert evaluation["repair_plan"]["upstream_media_shot_ids"] == ["SH-045"]
    assert evaluation["repair_plan"]["paid_provider_requests_authorized"] == 0


def test_pass_advances_to_human_final_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_id, root = _prepare(tmp_path)
    monkeypatch.setattr(qa, "require_qa_environment", lambda repo: _environment(tmp_path))
    monkeypatch.setattr(qa, "evaluate_automatic_qa", lambda *args, **kwargs: _pass_evaluation(episode_id))
    monkeypatch.setattr(qa, "_update_dependency_graph", lambda *args, **kwargs: None)
    result = run_automatic_qa_and_partial_repair(tmp_path)
    assert isinstance(result, AutomaticQAResult)
    assert result.status == "AWAITING_HUMAN_FINAL_REVIEW"
    state = json.loads((tmp_path / qa.ORCHESTRATOR_STATE_REL).read_text(encoding="utf-8"))
    assert state["status"] == "AWAITING_HUMAN_FINAL_REVIEW"
    assert state["next_stage"] == "HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1"
    assert (root / qa.QA_REPORT_REL).is_file()
    status = load_automatic_qa_status(tmp_path)
    assert status["complete"] is True


def test_local_repair_invalidates_only_selected_shot_and_reuses_rest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_id, root = _prepare(tmp_path)
    blocked = {
        **_pass_evaluation(episode_id),
        "status": "BLOCKED",
        "blocking_issue_count": 1,
        "quality_score": 80,
        "issues": [
            {
                "code": "SHOT_OUTPUT_HASH_MISMATCH",
                "severity": "BLOCKING",
                "scope": "SHOT",
                "detail": "hash",
                "repair_class": "LOCAL_SHOT_RERENDER",
                "shot_id": "SH-001",
            }
        ],
        "repair_plan": {
            "local_shot_ids": ["SH-001"],
            "local_final_remux": False,
            "upstream_media_shot_ids": [],
            "upstream_audio_required": False,
            "manual_blocking_review_required": False,
            "paid_provider_requests_authorized": 0,
        },
    }
    evaluations = iter([blocked, _pass_evaluation(episode_id)])
    monkeypatch.setattr(qa, "require_qa_environment", lambda repo: _environment(tmp_path))
    monkeypatch.setattr(qa, "evaluate_automatic_qa", lambda *args, **kwargs: next(evaluations))
    monkeypatch.setattr(qa, "_update_dependency_graph", lambda *args, **kwargs: None)

    def fake_montage(repo):
        shot = root / qa.SHOT_DIR_REL / "SH-001.mp4"
        receipt = root / qa.SHOT_RECEIPT_DIR_REL / "SH-001-receipt.json"
        shot.write_bytes(b"repaired")
        _write(receipt, {"status": "COMPLETE"})
        final = root / qa.FINAL_MASTER_REL
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"remuxed")
        return SimpleNamespace(reused_shot_count=69)

    monkeypatch.setattr(qa, "run_structural_montage_final_render", fake_montage)
    untouched = root / qa.SHOT_DIR_REL / "SH-002.mp4"
    untouched_before = untouched.read_bytes()
    result = run_automatic_qa_and_partial_repair(tmp_path)
    assert result.repair_passes == 1
    assert result.repaired_shot_count == 1
    assert result.reused_shot_count == 69
    assert untouched.read_bytes() == untouched_before


def test_upstream_defect_blocks_without_provider_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_id, root = _prepare(tmp_path)
    blocked = {
        **_pass_evaluation(episode_id),
        "status": "BLOCKED",
        "blocking_issue_count": 1,
        "quality_score": 80,
        "issues": [],
        "repair_plan": {
            "local_shot_ids": [],
            "local_final_remux": False,
            "upstream_media_shot_ids": ["SH-045"],
            "upstream_audio_required": False,
            "manual_blocking_review_required": False,
            "paid_provider_requests_authorized": 0,
        },
    }
    monkeypatch.setattr(qa, "require_qa_environment", lambda repo: _environment(tmp_path))
    monkeypatch.setattr(qa, "evaluate_automatic_qa", lambda *args, **kwargs: blocked)
    monkeypatch.setattr(qa, "_update_dependency_graph", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        qa,
        "run_structural_montage_final_render",
        lambda *args, **kwargs: pytest.fail("montage must not run for an upstream source defect"),
    )
    result = run_automatic_qa_and_partial_repair(tmp_path)
    assert result.status == "AUTOMATIC_QA_BLOCKED"
    assert result.repair_passes == 0
    report = json.loads((root / qa.QA_REPORT_REL).read_text(encoding="utf-8"))
    assert report["paid_provider_requests"] == 0
    state = json.loads((tmp_path / qa.ORCHESTRATOR_STATE_REL).read_text(encoding="utf-8"))
    assert state["next_stage"] == "DESKTOP_MEDIA_EXECUTION"
