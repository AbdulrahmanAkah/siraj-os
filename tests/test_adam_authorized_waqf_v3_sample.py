from __future__ import annotations

import pytest

from src.application.adam_authorized_waqf_v3_sample import (
    EXPECTED_AUTHORIZED_MAXIMUM_USD,
    EXPECTED_CHARACTER_COUNT,
    EXPECTED_TEXT,
    AuthorizedWaqfSampleError,
    validate_authorization_request,
)


def valid_request() -> dict:
    return {
        "automatic_resubmission": "FORBIDDEN",
        "block_id": "VB-001-01",
        "character_count_unicode": 263,
        "episode_id": "episode-001-adam",
        "full_episode_tts_authorized": False,
        "hidden_paid_retry": "FORBIDDEN",
        "internal_reserve_share_usd": 0.069418,
        "maximum_provider_requests": 1,
        "model_id": "eleven_multilingual_v2",
        "output_format": "mp3_44100_128",
        "queue_id": "TTS-WAQF-V3-SAMPLE-VB-001-01",
        "reason": "LINGUISTICALLY_HARDENED_ACTUAL_STOP_WAQF",
        "sample_generation_authorized": False,
        "segment_id": "ADAM-SEQUENCE-01",
        "status": "AWAITING_EXPLICIT_SECOND_SAMPLE_AUTHORIZATION",
        "suggested_authorization_ceiling_usd": 0.07,
        "text_ar": EXPECTED_TEXT,
        "voice_id": "XdoLPWNt7ytn6BtU4FBf",
        "voice_settings": {
            "similarity_boost": 0.75,
            "stability": 0.38,
            "style": 0.42,
            "use_speaker_boost": True,
        },
    }


def test_authorized_request_is_exactly_locked() -> None:
    validate_authorization_request(
        valid_request(),
        confirmed_maximum_usd=EXPECTED_AUTHORIZED_MAXIMUM_USD,
    )
    assert len(EXPECTED_TEXT) == EXPECTED_CHARACTER_COUNT
    assert "مَنَعَهْ، وَلَا" in EXPECTED_TEXT
    assert "يَرَى، وَيَفْهَمُ،" in EXPECTED_TEXT


def test_changed_text_is_rejected() -> None:
    request = valid_request()
    request["text_ar"] += " تغيير"
    with pytest.raises(
        AuthorizedWaqfSampleError,
        match="AUTHORIZED_WAQF_SAMPLE_TEXT_CHANGED",
    ):
        validate_authorization_request(
            request,
            confirmed_maximum_usd=0.07,
        )


def test_higher_maximum_is_rejected() -> None:
    with pytest.raises(
        AuthorizedWaqfSampleError,
        match="EXPLICIT_AUTHORIZATION_MAXIMUM_MISMATCH",
    ):
        validate_authorization_request(
            valid_request(),
            confirmed_maximum_usd=0.08,
        )


def test_full_episode_authorization_is_rejected() -> None:
    request = valid_request()
    request["full_episode_tts_authorized"] = True
    with pytest.raises(
        AuthorizedWaqfSampleError,
        match="FULL_EPISODE_TTS_MUST_REMAIN_UNAUTHORIZED",
    ):
        validate_authorization_request(
            request,
            confirmed_maximum_usd=0.07,
        )
