from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import wave

import pytest

from src.application.local_video_production.openai_speech_provider_v1 import (
    OPENAI_SPEECH_PROVIDER_ID,
    OpenAISpeechAuthenticationError,
    OpenAISpeechConfiguration,
    OpenAISpeechProvider,
    OpenAISpeechRateLimitError,
    OpenAISpeechRequestError,
    build_openai_speech_payload,
    classify_http_error,
)
from src.application.local_video_production.production_tts_v1 import (
    TTSSegmentRequest,
    inspect_pcm_wav,
)


def segment_request() -> TTSSegmentRequest:
    return TTSSegmentRequest(
        segment_id="segment-001",
        text="هذا تعليق عربي تجريبي.",
        language="ar",
        model="gpt-4o-mini-tts",
        voice_id="cedar",
        speed=1.0,
        instructions=(
            "اقرأ بأسلوب وثائقي هادئ."
        ),
        response_format="wav",
        sample_rate=24000,
    )


def wav_bytes() -> bytes:
    buffer = BytesIO()

    with wave.open(
        buffer,
        "wb",
    ) as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(
            b"\x00\x00" * 2400
        )

    return buffer.getvalue()


class FakeResponse:
    def __init__(
        self,
        content: bytes,
    ) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        return None


def test_payload_contains_supported_fields() -> None:
    payload = build_openai_speech_payload(
        segment_request()
    )

    assert payload["model"] == (
        "gpt-4o-mini-tts"
    )
    assert payload["voice"] == "cedar"
    assert payload["response_format"] == "wav"
    assert "instructions" in payload


def test_payload_rejects_excessive_text() -> None:
    request = segment_request()

    request = TTSSegmentRequest(
        segment_id=request.segment_id,
        text="ا" * 4097,
        language=request.language,
        model=request.model,
        voice_id=request.voice_id,
        speed=request.speed,
        instructions=request.instructions,
        response_format=request.response_format,
        sample_rate=request.sample_rate,
    )

    with pytest.raises(
        OpenAISpeechRequestError,
        match="OPENAI_SPEECH_TEXT_TOO_LONG",
    ):
        build_openai_speech_payload(
            request
        )


def test_error_classification() -> None:
    assert isinstance(
        classify_http_error(
            401,
            "invalid key",
        ),
        OpenAISpeechAuthenticationError,
    )

    assert isinstance(
        classify_http_error(
            429,
            "rate limited",
        ),
        OpenAISpeechRateLimitError,
    )


def test_provider_writes_mocked_wav(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def opener(
        request,
        timeout,
    ) -> FakeResponse:
        captured["url"] = (
            request.full_url
        )
        captured["timeout"] = timeout
        captured["authorization"] = (
            request.headers[
                "Authorization"
            ]
        )
        captured["payload"] = json.loads(
            request.data.decode(
                "utf-8"
            )
        )

        return FakeResponse(
            wav_bytes()
        )

    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key-not-real",
    )

    provider = OpenAISpeechProvider(
        configuration=(
            OpenAISpeechConfiguration(
                endpoint=(
                    "https://example.invalid/"
                    "v1/audio/speech"
                ),
                timeout_seconds=12.0,
            )
        ),
        opener=opener,
    )

    output = tmp_path / "speech.wav"

    provider.synthesize_segment(
        segment_request(),
        output,
    )

    assert output.is_file()
    assert provider.provider_id == (
        OPENAI_SPEECH_PROVIDER_ID
    )
    assert captured["timeout"] == 12.0
    assert captured["authorization"] == (
        "Bearer test-key-not-real"
    )
    assert captured["payload"]["voice"] == (
        "cedar"
    )

    info = inspect_pcm_wav(
        output
    )

    assert info["sample_rate"] == 24000
    assert info["channels"] == 1


def test_missing_api_key_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )

    provider = OpenAISpeechProvider()

    with pytest.raises(
        OpenAISpeechAuthenticationError,
        match="OPENAI_API_KEY_MISSING",
    ):
        provider.synthesize_segment(
            segment_request(),
            tmp_path / "speech.wav",
        )