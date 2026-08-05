from __future__ import annotations

import json
from pathlib import Path

from src.application.runware_image_model_routing_v1 import (
    SEEDREAM_MODEL,
    build_runware_image_task,
)
from src.application.runware_seedream_negative_prompt_recovery_v1 import (
    REJECTION_CODE,
    classify_seedream_negative_prompt_rejection,
    prepare_runware_task_for_submission,
    repair_runtime_seedream_negative_prompt_failure,
)


def _seedream_shot() -> dict:
    return {
        "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
        "image_model_role": "ENVIRONMENT_WIDE",
        "runware_positive_prompt_en": "A cinematic desert environment",
        "runware_negative_prompt_en": "text, watermark, distorted anatomy",
    }


def test_seedream_builder_omits_negative_prompt():
    task = build_runware_image_task(
        _seedream_shot(),
        "00000000-0000-4000-8000-000000000001",
    )
    assert task["model"] == SEEDREAM_MODEL
    assert "negativePrompt" not in task


def test_submission_sanitizer_is_defensive():
    task = prepare_runware_task_for_submission(
        {
            "model": SEEDREAM_MODEL,
            "positivePrompt": "test",
            "negativePrompt": "bad",
        }
    )
    assert "negativePrompt" not in task
    assert task["positivePrompt"] == "test"


def test_other_model_keeps_negative_prompt():
    task = prepare_runware_task_for_submission(
        {
            "model": "civitai:101055@128078",
            "positivePrompt": "test",
            "negativePrompt": "bad",
        }
    )
    assert task["negativePrompt"] == "bad"


def test_exact_terminal_rejection_is_classified_safe():
    rejection = classify_seedream_negative_prompt_rejection(
        {
            "errors": [
                {
                    "code": REJECTION_CODE,
                    "baseModelArchitecture": "seedream_5_pro",
                }
            ],
            "data": [],
        },
        {"model": SEEDREAM_MODEL},
    )
    assert rejection is not None
    assert rejection["safe_to_reauthorize"] is True


def test_runtime_repair_archives_lock_and_resets_queue(tmp_path: Path):
    repo = tmp_path / "repo"
    episode = repo / "projects/episode-001-adam"
    state_path = (
        repo
        / "projects/_orchestrator/"
        "autonomous-episode-orchestrator-state-v1.json"
    )
    queue_path = episode / "orchestration/media-production-queue-v1.json"
    lock_path = (
        episode
        / "orchestration/media-execution/locks/"
        "IMG-SH-001-attempt-01.json"
    )
    state_path.parent.mkdir(parents=True)
    queue_path.parent.mkdir(parents=True)
    lock_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "current_episode_id": "episode-001-adam",
                "status": "DESKTOP_MEDIA_EXECUTION_ACTIVE",
                "stage": "DESKTOP_MEDIA_EXECUTION",
            }
        ),
        encoding="utf-8",
    )
    queue_path.write_text(
        json.dumps(
            {
                "queues": {
                    "runware_images": [
                        {
                            "queue_id": "IMG-SH-001",
                            "status": "SUBMISSION_LOCKED",
                            "task_uuid": "old",
                            "task_draft": {
                                "model": SEEDREAM_MODEL,
                                "positivePrompt": "test",
                                "negativePrompt": "bad",
                            },
                        }
                    ],
                    "runware_videos": [],
                    "local_graphics": [],
                    "elevenlabs_tts": [],
                }
            }
        ),
        encoding="utf-8",
    )
    lock_path.write_text(
        json.dumps(
            {
                "queue_id": "IMG-SH-001",
                "media_kind": "RUNWARE_IMAGE",
                "status": "NETWORK_RESULT_UNKNOWN_USE_RECOVERY",
                "request_payload": [
                    {
                        "model": SEEDREAM_MODEL,
                        "positivePrompt": "test",
                        "negativePrompt": "bad",
                    }
                ],
                "last_error": (
                    "RUNWARE_HTTP_ERROR:400:"
                    + json.dumps(
                        {
                            "data": [],
                            "errors": [
                                {
                                    "code": REJECTION_CODE,
                                    "baseModelArchitecture": "seedream_5_pro",
                                }
                            ],
                        }
                    )
                ),
            }
        ),
        encoding="utf-8",
    )

    result = repair_runtime_seedream_negative_prompt_failure(repo)
    assert result.provider_requests == 0
    assert result.seedream_tasks_sanitized == 1
    assert result.terminal_locks_archived == 1
    assert result.queue_items_reset == 1
    assert not lock_path.exists()
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    item = queue["queues"]["runware_images"][0]
    assert item["status"] == "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
    assert "negativePrompt" not in item["task_draft"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "MEDIA_QUEUE_READY"
