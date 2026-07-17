"""Configuration isolation tests for the v4 quality gate."""

from src.application.local_video_production.quality_gate_v4 import (
    VoiceProviderRegistry,
    VoiceProviderSelection,
)


def test_voice_provider_selection_is_configuration_driven() -> None:
    selection = VoiceProviderSelection("FUTURE_ELEVENLABS", "future-arabic-voice", "ar-IQ")
    registry = VoiceProviderRegistry()
    registry.register("FUTURE_ELEVENLABS", lambda configured: {"provider": configured.provider_identifier, "voice": configured.voice_identifier})
    assert registry.resolve(selection) == {"provider": "FUTURE_ELEVENLABS", "voice": "future-arabic-voice"}


def test_unregistered_voice_provider_is_rejected() -> None:
    registry = VoiceProviderRegistry()
    try:
        registry.resolve(VoiceProviderSelection("UNREGISTERED", "voice", "ar"))
    except ValueError as error:
        assert str(error) == "VOICE_PROVIDER_NOT_REGISTERED"
    else:
        raise AssertionError("unregistered providers cannot enter the quality gate")
