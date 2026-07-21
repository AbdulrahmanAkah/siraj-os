"""Central registration for the active Gemini production TTS path."""

from __future__ import annotations

from .edge_speech_provider_v1 import EdgeSpeechProvider
from .gemini_speech_provider_v1 import GeminiTTSConfiguration, GeminiTTSSpeechProvider
from .production_tts_v1 import TTSProviderRegistry
from .voice_cast_v2 import EDGE_SPEECH_PROVIDER_ID, GEMINI_TTS_PROVIDER_ID


def build_current_production_tts_registry(configuration: GeminiTTSConfiguration | None = None) -> TTSProviderRegistry:
    """Register Gemini and Edge only; paid and blocked providers never auto-run."""
    registry = TTSProviderRegistry()
    registry.register(GeminiTTSSpeechProvider(configuration))
    registry.register(EdgeSpeechProvider())
    return registry


def current_registered_provider_ids() -> tuple[str, str]:
    return (GEMINI_TTS_PROVIDER_ID, EDGE_SPEECH_PROVIDER_ID)
