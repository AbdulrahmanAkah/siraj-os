from __future__ import annotations

import pytest

from src.application.local_video_production.voice_provider_v1 import (
    VOICE_REQUEST_SCHEMA_V1,
    build_voice_segments,
    estimate_arabic_duration_ms,
    normalize_arabic_text,
    split_arabic_narration,
    validate_voice_request,
)


def sample_request() -> dict:
    return {
        "schema_version": (
            VOICE_REQUEST_SCHEMA_V1
        ),
        "request_id": "voice-test-001",
        "episode_id": "episode-001",
        "language": "ar",
        "text": (
            "بدأت القصة منذ زمن بعيد. "
            "ثم انتقل الناس إلى أرض أخرى."
        ),
        "voice": {
            "voice_id": "arabic-narrator",
            "speed": 1.0,
        },
        "pronunciation_map": {
            "SIRAJ": "سراج",
        },
        "segmentation": {
            "max_words": 12,
        },
        "output": {
            "audio": "audio/voice.wav",
            "report": "reports/voice.json",
        },
    }


def test_normalize_arabic_text_expands_honorific() -> None:
    result = normalize_arabic_text(
        "محمد ﷺ"
    )

    assert (
        "صلى الله عليه وسلم"
        in result
    )


def test_normalize_arabic_text_removes_diacritics() -> None:
    result = normalize_arabic_text(
        "السَّلَامُ عَلَيْكُمْ"
    )

    assert result == "السلام عليكم"


def test_duration_estimate_is_positive() -> None:
    result = estimate_arabic_duration_ms(
        "هذه جملة عربية قصيرة."
    )

    assert result > 0


def test_split_narration_creates_ordered_segments() -> None:
    result = split_arabic_narration(
        "الجملة الأولى. الجملة الثانية؟"
    )

    assert len(result) == 2
    assert result[0].order == 1
    assert result[1].order == 2
    assert result[0].segment_id == (
        "voice-segment-001"
    )


def test_long_sentence_is_chunked() -> None:
    text = " ".join(
        f"كلمة{index}"
        for index in range(20)
    )

    result = split_arabic_narration(
        text,
        max_words=6,
    )

    assert len(result) == 4


def test_valid_request_passes() -> None:
    validate_voice_request(
        sample_request()
    )


def test_invalid_speed_is_rejected() -> None:
    request = sample_request()
    request["voice"]["speed"] = 2.0

    with pytest.raises(
        ValueError,
        match="VOICE_SPEED_INVALID",
    ):
        validate_voice_request(
            request
        )


def test_build_voice_segments_uses_request() -> None:
    result = build_voice_segments(
        sample_request()
    )

    assert len(result) == 2
    assert all(
        segment.estimated_duration_ms > 0
        for segment in result
    )