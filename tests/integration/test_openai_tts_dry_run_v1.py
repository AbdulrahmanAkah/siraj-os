from __future__ import annotations

from pathlib import Path

from src.application.local_video_production.openai_speech_provider_v1 import (
    OpenAISpeechProvider,
)
from src.application.local_video_production.production_tts_v1 import (
    TTSProviderRegistry,
    build_production_tts_plan,
)
from src.application.local_video_production.voice_provider_v1 import (
    VOICE_REQUEST_SCHEMA_V1,
)


def request_fixture() -> dict:
    return {
        "schema_version": (
            VOICE_REQUEST_SCHEMA_V1
        ),
        "request_id": "dry-run-test",
        "episode_id": "episode-test",
        "language": "ar",
        "text": (
            "هذه الجملة الأولى. "
            "وهذه الجملة الثانية."
        ),
        "voice": {
            "voice_id": "cedar",
            "speed": 1.0,
        },
        "segmentation": {
            "max_words": 12,
        },
        "tts": {
            "provider_id": (
                "openai-speech-v1"
            ),
            "model": (
                "gpt-4o-mini-tts"
            ),
            "instructions": (
                "اقرأ بأسلوب وثائقي."
            ),
            "response_format": "wav",
            "sample_rate": 24000,
            "pause_ms": 150,
        },
        "output": {
            "audio": (
                "working/tts/final.wav"
            ),
            "report": (
                "manifests/tts.json"
            ),
        },
    }


def test_openai_provider_dry_run(
    tmp_path: Path,
) -> None:
    registry = TTSProviderRegistry()

    registry.register(
        OpenAISpeechProvider()
    )

    plan = build_production_tts_plan(
        request_fixture(),
        tmp_path,
        registry,
    )

    assert plan["status"] == "VALID"
    assert plan["dry_run"] is True
    assert (
        plan["external_api_called"]
        is False
    )
    assert plan["provider_id"] == (
        "openai-speech-v1"
    )
    assert plan["model"] == (
        "gpt-4o-mini-tts"
    )
    assert plan["voice_id"] == "cedar"
    assert plan["segment_count"] == 2
    assert plan["cache_misses"] == 2

    assert all(
        segment["character_count"] > 0
        for segment in plan["segments"]
    )