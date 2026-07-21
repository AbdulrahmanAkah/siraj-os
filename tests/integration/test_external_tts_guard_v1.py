from __future__ import annotations

import pytest

from src.application.local_video_production.external_tts_guard_v1 import (
    ExternalTTSGuardError,
    inspect_external_tts_guard,
    require_external_tts_authorization,
    require_external_tts_execution_authorization,
)


def test_guard_rejects_missing_provider_key() -> None:
    with pytest.raises(
        ExternalTTSGuardError,
        match="ELEVENLABS_API_KEY_MISSING",
    ):
        require_external_tts_authorization(
            "ELEVENLABS_API_KEY",
            {
                "SIRAJ_ALLOW_EXTERNAL_TTS": "YES",
            },
        )


def test_guard_rejects_missing_authorization() -> None:
    with pytest.raises(
        ExternalTTSGuardError,
        match="EXTERNAL_TTS_NOT_AUTHORIZED",
    ):
        require_external_tts_authorization(
            "ELEVENLABS_API_KEY",
            {
                "ELEVENLABS_API_KEY": "test-key",
            },
        )


def test_guard_requires_exact_yes() -> None:
    status = inspect_external_tts_guard(
        "ELEVENLABS_API_KEY",
        {
            "ELEVENLABS_API_KEY": "test-key",
            "SIRAJ_ALLOW_EXTERNAL_TTS": "yes",
        },
    )

    assert status.provider_api_key_present is True
    assert status.external_tts_authorized is False
    assert status.ready is False


def test_guard_accepts_both_conditions() -> None:
    status = require_external_tts_authorization(
        "ELEVENLABS_API_KEY",
        {
            "ELEVENLABS_API_KEY": "test-key",
            "SIRAJ_ALLOW_EXTERNAL_TTS": "YES",
        },
    )

    assert status.ready is True


def test_guard_rejects_empty_variable_name() -> None:
    with pytest.raises(
        ValueError,
        match="EXTERNAL_TTS_API_KEY_VARIABLE_REQUIRED",
    ):
        inspect_external_tts_guard(
            "",
            {},
        )


def test_generic_google_adc_execution_guard_needs_explicit_yes() -> None:
    with pytest.raises(ExternalTTSGuardError, match="EXTERNAL_TTS_NOT_AUTHORIZED"):
        require_external_tts_execution_authorization({})
    assert require_external_tts_execution_authorization({"SIRAJ_ALLOW_EXTERNAL_TTS": "YES"}) is None
