from __future__ import annotations

from src.application.local_video_production.production_tts_registry_v1 import (
    build_current_production_tts_registry,
    current_registered_provider_ids,
)
from src.application.local_video_production.voice_cast_v2 import ELEVENLABS_SPEECH_PROVIDER_ID


def test_current_registry_contains_gemini_and_edge_only() -> None:
    registry = build_current_production_tts_registry()
    assert registry.provider_ids() == tuple(sorted(current_registered_provider_ids()))
    assert ELEVENLABS_SPEECH_PROVIDER_ID not in registry.provider_ids()
