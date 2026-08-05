from __future__ import annotations

import json
from pathlib import Path
import uuid

import pytest

import src.application.desktop_media_execution_v1 as execution
from src.application.desktop_media_execution_v1 import (
    DesktopMediaExecutionError,
    execute_runware_item,
    media_queue_rows,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _prepare(tmp_path: Path) -> tuple[str, Path]:
    episode_id = "episode-002-test"
    root = tmp_path / "projects" / episode_id
    _write(
        tmp_path
        / "projects/_orchestrator/"
        "autonomous-episode-orchestrator-state-v1.json",
        {
            "current_episode_id": episode_id,
            "status": "MEDIA_QUEUE_READY",
            "stage": "RUNWARE_IMAGE_GENERATION",
        },
    )
    _write(
        root / "orchestration/media-production-queue-v1.json",
        {
            "schema_version": "siraj-media-production-queue-v1",
            "episode_id": episode_id,
            "queues": {
                "runware_images": [
                    {
                        "queue_id": "IMG-SH-001",
                        "queue_index": 1,
                        "shot_id": "SH-001",
                        "status": (
                            "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
                        ),
                        "selected_model": "bytedance:seedream@5.0-pro",
                        "maximum_authorized_usd": 0.15,
                        "task_draft": {
                            "taskType": "imageInference",
                            "taskUUID": "old-non-v4-value",
                            "model": "bytedance:seedream@5.0-pro",
                            "positivePrompt": "Historical environment.",
                            "width": 1424,
                            "height": 800,
                            "numberResults": 1,
                            "includeCost": True,
                        },
                        "output_path_relative": (
                            f"projects/{episode_id}/cinematic/"
                            "runware-images/SH-001/attempt-01.jpg"
                        ),
                    }
                ],
                "runware_videos": [],
                "local_graphics": [],
                "elevenlabs_tts": [],
            },
        },
    )
    return episode_id, root


def test_rows_expose_paid_limit(tmp_path: Path) -> None:
    _prepare(tmp_path)
    rows = media_queue_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0].media_kind == "RUNWARE_IMAGE"
    assert rows[0].maximum_authorized_usd == 0.15


def test_explicit_authorization_limit_must_match(tmp_path: Path) -> None:
    _prepare(tmp_path)
    with pytest.raises(
        DesktopMediaExecutionError,
        match="EXPLICIT_AUTHORIZATION_MAXIMUM_MISMATCH",
    ):
        execute_runware_item(
            tmp_path,
            "IMG-SH-001",
            "key",
            confirmed_maximum_usd=0.14,
        )


def test_runware_uses_uuid4_and_locks_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, root = _prepare(tmp_path)
    observed = {}

    def fake_post(api_key, tasks, timeout=60.0):
        del api_key, timeout
        task_uuid = tasks[0]["taskUUID"]
        observed["task_uuid"] = task_uuid
        lock = (
            root
            / "orchestration/media-execution/locks/"
            "IMG-SH-001-attempt-01.json"
        )
        observed["lock_existed_before_network"] = lock.is_file()
        return {
            "data": [
                {
                    "taskType": "imageInference",
                    "taskUUID": task_uuid,
                    "imageUUID": str(uuid.uuid4()),
                    "imageURL": "https://example.invalid/image.jpg",
                    "cost": 0.048,
                }
            ]
        }

    def fake_download(url, destination, timeout=240.0):
        del url, timeout
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"image-bytes")

    monkeypatch.setattr(execution, "_post_json", fake_post)
    monkeypatch.setattr(execution, "_download_url", fake_download)

    result = execute_runware_item(
        tmp_path,
        "IMG-SH-001",
        "key",
        confirmed_maximum_usd=0.15,
    )
    assert uuid.UUID(observed["task_uuid"]).version == 4
    assert observed["lock_existed_before_network"] is True
    assert result.actual_cost_usd == 0.048
    assert result.output_path.is_file()

    queue = json.loads(
        (
            root / "orchestration/media-production-queue-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert queue["queues"]["runware_images"][0]["status"] == "COMPLETE"


def test_existing_lock_blocks_resubmission(tmp_path: Path) -> None:
    _, root = _prepare(tmp_path)
    lock = (
        root
        / "orchestration/media-execution/locks/"
        "IMG-SH-001-attempt-01.json"
    )
    _write(lock, {"task_uuid": str(uuid.uuid4())})
    with pytest.raises(
        DesktopMediaExecutionError,
        match="ATTEMPT_ALREADY_LOCKED_USE_RECOVERY",
    ):
        execute_runware_item(
            tmp_path,
            "IMG-SH-001",
            "key",
            confirmed_maximum_usd=0.15,
        )
