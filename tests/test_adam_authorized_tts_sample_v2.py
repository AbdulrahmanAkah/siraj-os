from __future__ import annotations

import json

import pytest

from src.application.adam_authorized_tts_sample_v2 import (
    EXPECTED_AUTHORIZED_MAXIMUM_USD,
    EXPECTED_CHARACTER_COUNT,
    EXPECTED_TEXT,
    AuthorizedTtsSampleError,
    validate_authorization_request,
)


def valid_request() -> dict:
    return {
        "episode_id": "episode-001-adam",
        "queue_id": "TTS-SAMPLE-VB-001-01",
        "block_id": "VB-001-01",
        "segment_id": "ADAM-SEQUENCE-01",
        "voice_id": "XdoLPWNt7ytn6BtU4FBf",
        "model_id": "eleven_multilingual_v2",
        "output_format": "mp3_44100_128",
        "sample_generation_authorized": False,
        "status": "READY_FOR_EXPLICIT_SAMPLE_AUTHORIZATION",
        "text_ar": EXPECTED_TEXT,
        "character_count_unicode": EXPECTED_CHARACTER_COUNT,
        "suggested_authorization_ceiling_usd": 0.07,
        "hidden_paid_retry": "FORBIDDEN",
        "automatic_resubmission": "FORBIDDEN",
        "voice_settings": {
            "stability": 0.38,
            "similarity_boost": 0.75,
            "style": 0.42,
            "use_speaker_boost": True,
        },
    }


def test_authorized_request_is_exactly_locked() -> None:
    request = valid_request()
    validate_authorization_request(
        request,
        confirmed_maximum_usd=EXPECTED_AUTHORIZED_MAXIMUM_USD,
    )
    assert len(EXPECTED_TEXT) == 263


def test_changed_text_is_rejected() -> None:
    request = valid_request()
    request["text_ar"] += " تغيير"
    with pytest.raises(
        AuthorizedTtsSampleError,
        match="AUTHORIZED_SAMPLE_TEXT_CHANGED",
    ):
        validate_authorization_request(
            request,
            confirmed_maximum_usd=0.07,
        )


def test_higher_maximum_is_rejected() -> None:
    with pytest.raises(
        AuthorizedTtsSampleError,
        match="EXPLICIT_AUTHORIZATION_MAXIMUM_MISMATCH",
    ):
        validate_authorization_request(
            valid_request(),
            confirmed_maximum_usd=0.08,
        )
