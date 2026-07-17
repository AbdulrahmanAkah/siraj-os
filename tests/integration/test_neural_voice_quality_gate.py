"""Offline checks for the v4 production voice qualification gate."""

from __future__ import annotations

from io import BytesIO
import wave

from src.application.local_video_production.neural_voice import (
    AzureNeuralArabicVoiceProvider,
    AzureNeuralVoiceConfig,
    NeuralVoiceError,
    run_azure_voice_audition_gate,
    validate_wav_audio,
)
from src.application.ai_provider_openai_compatible import CredentialReference, ExternalAIExecutionPolicy


class _Resolver:
    def resolve(self, _reference):
        return None


def test_production_voice_gate_blocks_without_neural_credential(tmp_path) -> None:
    provider = AzureNeuralArabicVoiceProvider(
        AzureNeuralVoiceConfig("https://example.invalid/tts", CredentialReference("AZURE_SPEECH_KEY")),
        _Resolver(),
        ExternalAIExecutionPolicy(
            allow_external=True,
            approved=True,
            allowed_providers=("AZURE_NEURAL_TTS",),
            allowed_models=("azure-speech-neural",),
        ),
    )
    report = run_azure_voice_audition_gate(tmp_path, provider)
    assert report["status"] == "BLOCKED"
    assert report["reason"] == "AZURE_NEURAL_TTS_CREDENTIAL_UNAVAILABLE"
    assert (tmp_path / "voice-audition-report.json").is_file()


def test_production_voice_gate_rejects_espeak_named_provider(tmp_path) -> None:
    class EspeakOnlyForTest:
        provider_id = "ESPEAK_NG_ARABIC_LOCAL"

        def synthesize(self, _request):
            raise AssertionError("must never be called")

    try:
        run_azure_voice_audition_gate(tmp_path, EspeakOnlyForTest())
    except NeuralVoiceError as error:
        assert str(error) == "PRODUCTION_REQUIRES_NEURAL_VOICE_PROVIDER"
    else:
        raise AssertionError("eSpeak must be rejected in production")


def test_wav_header_without_audio_samples_is_rejected(tmp_path) -> None:
    empty = tmp_path / "azure-diagnostic.wav"
    with wave.open(str(empty), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24_000)
        output.writeframes(b"")
    try:
        validate_wav_audio(empty)
    except NeuralVoiceError as error:
        assert str(error) == "NEURAL_VOICE_WAV_TOO_SMALL"
    else:
        raise AssertionError("an empty Azure WAV header must not pass")
