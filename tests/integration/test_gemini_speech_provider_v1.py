from __future__ import annotations

from array import array
from io import BytesIO
from pathlib import Path
import wave

import pytest

from src.application.local_video_production.gemini_speech_provider_v1 import (
    GeminiTTSConfiguration,
    GeminiTTSDailyQuotaExhaustedError,
    GeminiTTSEmptyAudioError,
    GeminiTTSInvalidApiKeyError,
    GeminiTTSInvalidVoiceError,
    GeminiTTSRateLimitGuard,
    GeminiTTSRateLimitedError,
    GeminiTTSSpeechProvider,
    classify_gemini_tts_error,
    gemini_tts_manifest,
    load_gemini_tts_configuration,
)
from src.application.local_video_production.production_tts_v1 import TTSSegmentRequest, inspect_pcm_wav
from src.application.local_video_production.voice_cast_v2 import GEMINI_PRIMARY_MODEL, PRIMARY_VOICE_ID


def _pcm() -> bytes:
    return array("h", [800] * 2400).tobytes()


class _Inline:
    data = _pcm()
    mime_type = "audio/L16;rate=24000"


class _Part:
    inline_data = _Inline()


class _Content:
    parts = [_Part()]


class _Candidate:
    content = _Content()


class _Response:
    candidates = [_Candidate()]


class _Client:
    def __init__(self) -> None: self.calls = 0
    class models:
        pass


class _Models:
    def __init__(self, client: _Client) -> None: self.client = client
    def generate_content(self, **_: object) -> _Response:
        self.client.calls += 1
        return _Response()


class _Config:
    def __init__(self, **values: object) -> None: self.values = values


class _Types:
    GenerateContentConfig = _Config
    SpeechConfig = _Config
    VoiceConfig = _Config
    PrebuiltVoiceConfig = _Config


def _provider() -> tuple[GeminiTTSSpeechProvider, _Client]:
    client = _Client(); client.models = _Models(client)
    return GeminiTTSSpeechProvider(client=client, types_module=_Types), client


def _request(voice: str = PRIMARY_VOICE_ID, model: str = GEMINI_PRIMARY_MODEL) -> TTSSegmentRequest:
    return TTSSegmentRequest("segment", "\u0645\u0631\u062d\u0628\u0627 \u0628\u063a\u062f\u0627\u062f", "ar", model, voice, 1.0, "\u0627\u0642\u0631\u0623 \u0628\u0648\u0636\u0648\u062d.", "wav", 24000)


def test_fake_gemini_provider_writes_valid_wav_without_network(tmp_path: Path) -> None:
    provider, client = _provider()
    output = tmp_path / "voice.wav"
    provider.synthesize_segment(_request(), output)
    assert client.calls == 1
    assert inspect_pcm_wav(output)["sample_rate"] == 24000


def test_unapproved_voice_is_rejected_before_external_call(tmp_path: Path) -> None:
    provider, client = _provider()
    with pytest.raises(GeminiTTSInvalidVoiceError): provider.synthesize_segment(_request("NotApproved"), tmp_path / "bad.wav")
    assert client.calls == 0


def test_empty_audio_is_explicit_failure(tmp_path: Path) -> None:
    class EmptyModels(_Models):
        def generate_content(self, **_: object) -> object:
            self.client.calls += 1
            return type("R", (), {"candidates": []})()
    provider, client = _provider(); client.models = EmptyModels(client)
    with pytest.raises(GeminiTTSEmptyAudioError): provider.synthesize_segment(_request(), tmp_path / "empty.wav")
    assert client.calls == 1


def test_error_classification_never_retries_auth_or_quota() -> None:
    assert isinstance(classify_gemini_tts_error(RuntimeError("invalid api key")), GeminiTTSInvalidApiKeyError)
    assert isinstance(classify_gemini_tts_error(RuntimeError("RequestsPerMinute quota")), GeminiTTSRateLimitedError)
    assert isinstance(classify_gemini_tts_error(RuntimeError("RequestsPerDay quota")), GeminiTTSDailyQuotaExhaustedError)


def test_rate_guard_applies_per_model_limits() -> None:
    policy = type("P", (), {"requests_per_minute": 1, "requests_per_day": 2, "tokens_per_minute": 100})()
    guard = GeminiTTSRateLimitGuard(policy, clock=lambda: 1000.0)
    guard.acquire("model-a", "text")
    with pytest.raises(GeminiTTSRateLimitedError): guard.acquire("model-a", "text")
    guard.acquire("model-b", "text")


def test_manifest_and_configuration_limits_are_serializable_without_secret() -> None:
    config = load_gemini_tts_configuration({"SIRAJ_GEMINI_TTS_RPM": "2", "SIRAJ_GEMINI_TTS_RPD": "8", "SIRAJ_GEMINI_TTS_TPM": "9000"})
    manifest = gemini_tts_manifest(config)
    assert manifest["active_model"] == GEMINI_PRIMARY_MODEL
    assert manifest["quota_policy"]["requests_per_minute"] == 2
    assert "GEMINI_API_KEY" not in str(manifest)


def test_error_redacts_api_key() -> None:
    fake_key = "AIza" + "x" * 20
    error = classify_gemini_tts_error(RuntimeError(f"invalid api key {fake_key}"))
    assert fake_key not in str(error)
