from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.elevenlabs_key_validation_recovery_v1 import (
    ElevenLabsKeyValidationError,
    classify_elevenlabs_invalid_key_prefix_rejection,
    normalize_and_validate_elevenlabs_api_key,
    recover_invalid_elevenlabs_attempts,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_elevenlabs_key_prefix_validation() -> None:
    assert normalize_and_validate_elevenlabs_api_key("  sk_valid_test  ") == "sk_valid_test"
    with pytest.raises(ElevenLabsKeyValidationError, match="INVALID_PREFIX"):
        normalize_and_validate_elevenlabs_api_key("xi_invalid")
    with pytest.raises(ElevenLabsKeyValidationError, match="WHITESPACE"):
        normalize_and_validate_elevenlabs_api_key("sk_bad key")


def test_classifies_provider_prefix_rejection() -> None:
    rejection = classify_elevenlabs_invalid_key_prefix_rejection(
        {
            "detail": {
                "type": "authentication_error",
                "code": "invalid_api_key",
                "status": "invalid_api_key_prefix",
                "message": "API key must start with 'sk_'",
            }
        }
    )
    assert rejection is not None
    assert rejection["safe_to_reauthorize"] is True
    assert rejection["provider_request_billed"] is False


def test_runtime_recovery_archives_only_invalid_tts_lock(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    episode_id = "episode-001-adam"
    state_path = repo / "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
    queue_path = repo / "projects" / episode_id / "orchestration/media-production-queue-v1.json"
    lock_path = repo / "projects" / episode_id / "orchestration/media-execution/locks/TTS-SEG-005-B01-attempt-01.json"
    _write(
        state_path,
        {
            "current_episode_id": episode_id,
            "status": "DESKTOP_MEDIA_EXECUTION_ACTIVE",
            "stage": "DESKTOP_MEDIA_EXECUTION",
        },
    )
    _write(
        queue_path,
        {
            "queues": {
                "runware_images": [],
                "runware_videos": [],
                "local_graphics": [],
                "elevenlabs_tts": [
                    {
                        "queue_id": "TTS-SEG-004-B01",
                        "status": "COMPLETE",
                        "receipt_path_relative": "receipt.json",
                    },
                    {
                        "queue_id": "TTS-SEG-005-B01",
                        "status": "SUBMISSION_LOCKED",
                        "request_id": "old-request",
                    },
                ],
            }
        },
    )
    _write(
        lock_path,
        {
            "media_kind": "ELEVENLABS_TTS",
            "queue_id": "TTS-SEG-005-B01",
            "status": "PROVIDER_REJECTED",
            "last_error": "invalid_api_key_prefix API key must start with 'sk_'",
        },
    )
    result = recover_invalid_elevenlabs_attempts(repo)
    assert result.terminal_locks_archived == 1
    assert result.queue_items_reset == 1
    assert result.paid_items_reset == 0
    assert result.provider_requests == 0
    assert not lock_path.exists()
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    completed, reset = queue["queues"]["elevenlabs_tts"]
    assert completed["status"] == "COMPLETE"
    assert completed["receipt_path_relative"] == "receipt.json"
    assert reset["status"] == "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
    assert "request_id" not in reset
