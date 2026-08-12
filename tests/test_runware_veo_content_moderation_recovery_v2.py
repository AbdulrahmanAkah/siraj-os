import json
from pathlib import Path

from src.application.runware_seedream_negative_prompt_recovery_v1 import (
    classify_runware_terminal_provider_rejection_v2,
    reset_terminal_rejected_attempt_for_explicit_reauthorization,
)


def test_veo_invalid_provider_content_is_terminal_and_safe() -> None:
    error = {
        "errors": [
            {
                "code": "invalidProviderContent",
                "message": (
                    "Invalid content detected. The generated content was "
                    "flagged and rejected by Google's content moderation system."
                ),
                "responseContent": (
                    "Your current safety settings for people/face generation "
                    "filtered out 1 videos. You will not be charged."
                ),
            }
        ]
    }
    rejection = classify_runware_terminal_provider_rejection_v2(
        error,
        {
            "taskType": "videoInference",
            "model": "google:veo@3.1-lite",
        },
    )
    assert rejection is not None
    assert rejection["code"] == "invalidProviderContent"
    assert rejection["terminal"] is True
    assert rejection["safe_to_reauthorize"] is True
    assert rejection["billable_output_detected"] is False


def test_veo_content_rejection_with_output_is_not_safe() -> None:
    error = {
        "code": "invalidProviderContent",
        "message": (
            "Rejected by Google's content moderation system. "
            "people/face generation filtered out."
        ),
        "videoURL": "https://example.invalid/output.mp4",
    }
    rejection = classify_runware_terminal_provider_rejection_v2(
        error,
        {"model": "google:veo@3.1-lite"},
    )
    assert rejection is not None
    assert rejection["safe_to_reauthorize"] is False
    assert rejection["billable_output_detected"] is True


def test_reset_archives_veo_terminal_lock(tmp_path: Path) -> None:
    root = tmp_path / "media-execution"
    lock_dir = root / "locks"
    lock_dir.mkdir(parents=True)
    lock = lock_dir / "VID-SH-048-C02-attempt-01.json"

    payload = {
        "last_error": (
            "invalidProviderContent: rejected by Google's content moderation "
            "system; people/face generation filtered out. "
            "You will not be charged."
        ),
        "request_payload": [
            {
                "taskType": "videoInference",
                "model": "google:veo@3.1-lite",
            }
        ],
        "status": "NETWORK_RESULT_UNKNOWN_USE_RECOVERY",
    }
    lock.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    archived = reset_terminal_rejected_attempt_for_explicit_reauthorization(
        lock
    )
    assert archived is not None
    assert not lock.exists()
    assert archived.exists()
    assert archived.parent.name == "rejected-history"

def test_veo_minimal_invalid_provider_content_is_terminal() -> None:
    rejection = classify_runware_terminal_provider_rejection_v2(
        "RUNWARE_PROVIDER_ERROR:invalidProviderContent:Invalid content detected.",
        {
            "taskType": "videoInference",
            "model": "google:veo@3.1-lite",
        },
    )
    assert rejection is not None
    assert rejection["code"] == "invalidProviderContent"
    assert rejection["safe_to_reauthorize"] is True
    assert rejection["billable_output_detected"] is False

