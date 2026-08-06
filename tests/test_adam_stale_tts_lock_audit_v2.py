from __future__ import annotations

import json
from pathlib import Path

from src.application.adam_stale_tts_lock_audit_v2 import (
    audit_and_recover,
)


def test_no_lock_directory_is_safe_and_offline(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "projects/episode-001-adam").mkdir(parents=True)

    result = audit_and_recover(
        repo,
        episode_id="episode-001-adam",
    )

    assert result["status"] == "PASS_NO_TTS_LOCKS"
    assert result["provider_requests"] == 0
    assert result["paid_provider_requests"] == 0


def test_invalid_key_lock_is_archived(tmp_path: Path) -> None:
    repo = tmp_path
    lock_root = (
        repo
        / "projects/episode-001-adam/orchestration/media-execution/locks"
    )
    lock_root.mkdir(parents=True)
    lock_path = lock_root / "TTS-001-attempt-01.json"
    lock_path.write_text(
        json.dumps(
            {
                "media_kind": "ELEVENLABS_TTS",
                "queue_id": "TTS-001",
                "status": (
                    "PROVIDER_REJECTED_TERMINAL_"
                    "REAUTHORIZATION_REQUIRED"
                ),
                "last_error": "api key must start with 'sk_'",
            }
        ),
        encoding="utf-8",
    )

    result = audit_and_recover(
        repo,
        episode_id="episode-001-adam",
    )

    assert result["invalid_key_locks_archived"] == 1
    assert result["provider_requests"] == 0
    assert result["paid_provider_requests"] == 0
    assert not lock_path.exists()
