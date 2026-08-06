from __future__ import annotations

import hashlib
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


def _luna_image_certification() -> dict:
    positive = (
        "A restrained premium cinematic wide shot of a weathered historical "
        "environment, layered basalt foreground leading into a deep clay and "
        "stone landscape, 32mm lens, controlled low dolly perspective, amber "
        "rim light through suspended dust, tactile mineral textures, coherent "
        "foreground midground and background separation, one clear visual "
        "focus, stable geometry, no visible supernatural being, no text or "
        "logo, no morphing, no duplicate structures."
    )
    negative = (
        "no text, no logo, no watermark, no malformed geometry, "
        "no duplicate forms, no modern objects"
    )
    return {
        "schema_version": "siraj-luna-prompt-certification-v2",
        "release": "SIRAJ_LUNA_CINEMATIC_PROMPT_DIRECTOR_V2",
        "status": "PASS",
        "prompt_id": "PROMPT-001",
        "shot_id": "SH-001",
        "prompt_kind": "IMAGE_GENERATION",
        "provider": "RUNWARE",
        "model": "bytedance:seedream@5.0-pro",
        "authorship": "REWRITTEN_BY_LUNA",
        "luna_model": "gpt-5.6-luna",
        "luna_response_id": "resp_test_luna_prompt_certification",
        "luna_batch_id": "LUNA-PROMPT-BATCH-01",
        "rewrite_iterations_internal": 2,
        "rewrite_reason_ar": (
            "تحويل المسودة العامة إلى توجيه تصوير سينمائي محدد."
        ),
        "art_direction_ar": (
            "لقطة تاريخية واسعة ذات عمق طبقي وإضاءة كهرمانية مضبوطة."
        ),
        "cinematic_blueprint": {
            "subject": "weathered historical environment",
            "action": "controlled atmospheric drift",
            "environment": "basalt clay and stone landscape",
            "composition": "layered foreground midground background",
            "camera": "low controlled dolly perspective",
            "lens": "32mm",
            "lighting": "amber rim light through dust",
            "color_palette": "charcoal ochre amber",
            "materials": "basalt clay stone mineral dust",
            "atmosphere": "restrained suspended dust",
            "temporal_motion": "minimal coherent environmental drift",
            "continuity": "stable geometry and light direction",
            "safety": "no visible supernatural being",
        },
        "quality_scores": {
            "narrative_function": 10,
            "subject_and_action_clarity": 10,
            "composition_and_depth": 10,
            "camera_and_lens": 10,
            "lighting_and_color": 10,
            "materials_and_atmosphere": 10,
            "motion_and_temporal_logic": 9,
            "continuity": 10,
            "provider_specificity": 10,
            "religious_safety_and_artifact_prevention": 10,
        },
        "final_score": 99,
        "quality_threshold": 95,
        "blocking_flags": [],
        "certified_positive_prompt_en": positive,
        "certified_negative_prompt_en": negative,
        "negative_prompt_delivery": "EMBEDDED_AS_POSITIVE_CONSTRAINTS",
        "positive_prompt_sha256": hashlib.sha256(
            positive.encode("utf-8")
        ).hexdigest(),
        "negative_prompt_sha256": hashlib.sha256(
            negative.encode("utf-8")
        ).hexdigest(),
        "source_prompt_sha256": hashlib.sha256(
            b"Historical environment.\n--NEGATIVE--\n"
        ).hexdigest(),
        "certified_at_utc": "2026-08-06T12:00:00Z",
    }


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
                        "luna_prompt_certification_v2": _luna_image_certification(),
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
    lock_payload = json.loads(
        (
            root
            / "orchestration/media-execution/locks/"
            "IMG-SH-001-attempt-01.json"
        ).read_text(encoding="utf-8")
    )
    assert lock_payload["luna_prompt_certification_v2"][
        "luna_response_id"
    ] == "resp_test_luna_prompt_certification"
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

def test_uncertified_runware_item_is_blocked_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, root = _prepare(tmp_path)
    queue_path = (
        root / "orchestration/media-production-queue-v1.json"
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    item = queue["queues"]["runware_images"][0]
    item.pop("luna_prompt_certification_v2", None)
    _write(queue_path, queue)

    network_called = False

    def forbidden_post(*args, **kwargs):
        nonlocal network_called
        network_called = True
        raise AssertionError("network must not be called")

    monkeypatch.setattr(execution, "_post_json", forbidden_post)

    with pytest.raises(
        DesktopMediaExecutionError,
        match="LUNA_PROMPT_CERTIFICATION_REQUIRED_BEFORE_PROVIDER_EXECUTION",
    ):
        execute_runware_item(
            tmp_path,
            "IMG-SH-001",
            "key",
            confirmed_maximum_usd=0.15,
        )

    assert network_called is False
    lock = (
        root
        / "orchestration/media-execution/locks/"
        "IMG-SH-001-attempt-01.json"
    )
    assert lock.exists() is False


def test_runware_recovery_uses_locked_luna_certification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, root = _prepare(tmp_path)
    queue_path = (
        root / "orchestration/media-production-queue-v1.json"
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    item = queue["queues"]["runware_images"][0]
    certification = item["luna_prompt_certification_v2"]
    task_uuid = str(uuid.uuid4())
    task = dict(item["task_draft"])
    task["taskUUID"] = task_uuid

    lock = (
        root
        / "orchestration/media-execution/locks/"
        "IMG-SH-001-attempt-01.json"
    )
    _write(
        lock,
        {
            "schema_version": "siraj-desktop-media-submission-lock-v1",
            "task_uuid": task_uuid,
            "status": "SUBMITTED_POLLING",
            "request_payload": [task],
            "luna_prompt_certification_v2": certification,
        },
    )

    poll_called = False

    def fake_poll(
        api_key,
        observed_task_uuid,
        kind,
        *,
        progress=None,
    ):
        nonlocal poll_called
        del api_key, progress
        poll_called = True
        assert observed_task_uuid == task_uuid
        assert kind == "RUNWARE_IMAGE"
        return {
            "taskType": "imageInference",
            "taskUUID": task_uuid,
            "imageUUID": str(uuid.uuid4()),
            "imageURL": "https://example.invalid/recovered.jpg",
            "cost": 0.047,
        }

    def fake_download(url, destination, timeout=240.0):
        del url, timeout
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"recovered-image")

    def forbidden_post(*args, **kwargs):
        raise AssertionError("recovery must not resubmit")

    monkeypatch.setattr(execution, "_poll_runware", fake_poll)
    monkeypatch.setattr(execution, "_download_url", fake_download)
    monkeypatch.setattr(execution, "_post_json", forbidden_post)

    result = execute_runware_item(
        tmp_path,
        "IMG-SH-001",
        "key",
        confirmed_maximum_usd=0.15,
        recovery_only=True,
    )
    assert poll_called is True
    assert result.actual_cost_usd == 0.047

    receipt = json.loads(
        (
            root
            / "orchestration/media-execution/receipts/"
            "IMG-SH-001-attempt-01-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["luna_prompt_certification_v2"][
        "luna_response_id"
    ] == "resp_test_luna_prompt_certification"
