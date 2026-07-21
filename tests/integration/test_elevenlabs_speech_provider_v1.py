from __future__ import annotations

from pathlib import Path

import pytest

from src.application.local_video_production.elevenlabs_speech_provider_v1 import (
    ELEVENLABS_SPEECH_PROVIDER_ID,
    ElevenLabsAuthenticationError,
    ElevenLabsRateLimitError,
    ElevenLabsRequestError,
    ElevenLabsSubscriptionBlockedError,
    build_elevenlabs_payload,
    classify_elevenlabs_http_error,
    resolve_elevenlabs_api_key,
    ElevenLabsSpeechConfiguration,
)
from src.application.local_video_production.production_tts_v1 import (
    TTSSegmentRequest,
)


def request_fixture() -> TTSSegmentRequest:
    return TTSSegmentRequest(
        segment_id="segment-001",
        text="بدأت القصة من بغداد.",
        language="ar",
        model="eleven_multilingual_v2",
        voice_id="test-voice-id",
        speed=1.0,
        instructions=None,
        response_format="wav",
        sample_rate=44100,
    )


def test_payload_is_multilingual() -> None:
    payload = build_elevenlabs_payload(
        request_fixture()
    )

    assert payload["model_id"] == (
        "eleven_multilingual_v2"
    )
    assert payload["text"] == (
        "بدأت القصة من بغداد."
    )


def test_provider_id_is_stable() -> None:
    assert ELEVENLABS_SPEECH_PROVIDER_ID == (
        "elevenlabs-speech-v1"
    )


def test_http_error_classification() -> None:
    assert isinstance(
        classify_elevenlabs_http_error(
            401,
            "invalid key",
        ),
        ElevenLabsAuthenticationError,
    )

    assert isinstance(
        classify_elevenlabs_http_error(
            402,
            "subscription required",
        ),
        ElevenLabsSubscriptionBlockedError,
    )

    assert isinstance(
        classify_elevenlabs_http_error(
            429,
            "quota reached",
        ),
        ElevenLabsRateLimitError,
    )

    assert isinstance(
        classify_elevenlabs_http_error(
            400,
            "bad request",
        ),
        ElevenLabsRequestError,
    )


def test_missing_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "ELEVENLABS_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ElevenLabsAuthenticationError,
        match="ELEVENLABS_API_KEY_MISSING",
    ):
        resolve_elevenlabs_api_key(
            ElevenLabsSpeechConfiguration()
        )
