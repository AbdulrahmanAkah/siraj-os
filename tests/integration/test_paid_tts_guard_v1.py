from __future__ import annotations

import pytest

from src.application.local_video_production.paid_tts_guard_v1 import (
    PaidTTSGuardError,
    inspect_paid_tts_guard,
    require_paid_tts_authorization,
)


def test_guard_rejects_missing_api_key() -> None:
    environment = {
        "SIRAJ_ALLOW_PAID_TTS": "YES",
    }

    with pytest.raises(
        PaidTTSGuardError,
        match="OPENAI_API_KEY_MISSING",
    ):
        require_paid_tts_authorization(
            environment
        )


def test_guard_rejects_missing_consent() -> None:
    environment = {
        "OPENAI_API_KEY": "test-key",
    }

    with pytest.raises(
        PaidTTSGuardError,
        match="PAID_TTS_NOT_AUTHORIZED",
    ):
        require_paid_tts_authorization(
            environment
        )


def test_guard_requires_exact_yes() -> None:
    status = inspect_paid_tts_guard(
        {
            "OPENAI_API_KEY": "test-key",
            "SIRAJ_ALLOW_PAID_TTS": "yes",
        }
    )

    assert status.api_key_present is True
    assert (
        status.paid_tts_authorized
        is False
    )
    assert status.ready is False


def test_guard_accepts_both_conditions() -> None:
    status = require_paid_tts_authorization(
        {
            "OPENAI_API_KEY": "test-key",
            "SIRAJ_ALLOW_PAID_TTS": "YES",
        }
    )

    assert status.ready is True