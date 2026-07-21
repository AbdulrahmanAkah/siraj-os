from __future__ import annotations

import json
import os
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

PROJECT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project"
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from src.application.local_video_production.elevenlabs_speech_provider_v1 import (
    ELEVENLABS_RETRYABLE_ERRORS,
    ElevenLabsSpeechProvider,
)
from src.application.local_video_production.external_tts_guard_v1 import (
    require_external_tts_authorization,
)
from src.application.local_video_production.production_tts_v1 import (
    ProductionTTSOrchestrator,
    TTSProviderRegistry,
    TTSRetryPolicy,
)
from src.application.local_video_production.voice_provider_v1 import (
    VOICE_REQUEST_SCHEMA_V1,
    atomic_write_json,
)
from src.application.local_video_production.voice_roster_v1 import (
    get_primary_voice,
)


def main() -> int:
    if os.environ.get("SIRAJ_ENABLE_PREFERRED_PAID_TTS", "").strip() != "YES":
        print(json.dumps({"status": "BLOCKED_BY_SUBSCRIPTION", "provider_id": "elevenlabs-speech-v1"}, sort_keys=True))
        return 2

    require_external_tts_authorization(
        "ELEVENLABS_API_KEY"
    )

    selected_voice = (
        get_primary_voice()
    )

    request = {
        "schema_version": (
            VOICE_REQUEST_SCHEMA_V1
        ),
        "request_id": (
            "elevenlabs-preferred-paid-v1"
        ),
        "episode_id": (
            "elevenlabs-arabic-preferred-paid-smoke-test"
        ),
        "language": "ar",
        "text": (
            "بدأت القصة من بغداد، "
            "مدينة العلم والحضارة."
        ),
        "voice": {
            "voice_id": (
                selected_voice.voice_id
            ),
            "speed": 1.0,
        },
        "segmentation": {
            "max_words": 20,
        },
        "tts": {
            "provider_id": (
                "elevenlabs-speech-v1"
            ),
            "model": (
                "eleven_multilingual_v2"
            ),
            "response_format": "wav",
            "sample_rate": 44100,
            "pause_ms": 160,
        },
        "output": {
            "audio": (
                "working/voice-v1/"
                "elevenlabs-primary-arabic.wav"
            ),
            "report": (
                "manifests/"
                "elevenlabs-primary-arabic-report.json"
            ),
        },
    }

    request_path = (
        PROJECT_ROOT
        / "manifests"
        / "elevenlabs-primary-arabic-request.json"
    )

    atomic_write_json(
        request_path,
        request,
    )

    registry = TTSProviderRegistry()

    registry.register(
        ElevenLabsSpeechProvider()
    )

    orchestrator = ProductionTTSOrchestrator(
        registry=registry,
        retry_policy=TTSRetryPolicy(
            maximum_attempts=3,
            initial_delay_seconds=1.0,
            backoff_multiplier=2.0,
            maximum_delay_seconds=4.0,
        ),
        retryable_exception=(
            ELEVENLABS_RETRYABLE_ERRORS
        ),
    )

    result = orchestrator.synthesize(
        request=request,
        project_root=PROJECT_ROOT,
    )

    if result.status != "VALID":
        raise RuntimeError(
            "ELEVENLABS_PREFERRED_PAID_TTS_INVALID"
        )

    if result.segment_count != 1:
        raise RuntimeError(
            "ELEVENLABS_SMOKE_TEST_MUST_USE_ONE_SEGMENT"
        )

    print(
        json.dumps(
            {
                "status": result.status,
                "provider_id": (
                    result.provider_id
                ),
                "voice_id": (
                    selected_voice.voice_id
                ),
                "voice_role": (
                    "PRIMARY_NARRATOR"
                ),
                "segment_count": (
                    result.segment_count
                ),
                "cache_hits": (
                    result.cache_hits
                ),
                "cache_misses": (
                    result.cache_misses
                ),
                "output": (
                    result.output_path
                ),
                "report": (
                    result.report_path
                ),
                "output_sha256": (
                    result.output_sha256
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
