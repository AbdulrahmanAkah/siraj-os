from __future__ import annotations

import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

PROJECT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project"
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from src.application.local_video_production.openai_speech_provider_v1 import (
    OPENAI_SPEECH_RETRYABLE_ERRORS,
    OpenAISpeechProvider,
)
from src.application.local_video_production.paid_tts_guard_v1 import (
    require_paid_tts_authorization,
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


def main() -> int:
    require_paid_tts_authorization()

    request = {
        "schema_version": (
            VOICE_REQUEST_SCHEMA_V1
        ),
        "request_id": (
            "openai-live-guarded-v1"
        ),
        "episode_id": (
            "production-tts-live-smoke-test"
        ),
        "language": "ar",
        "text": (
            "بدأت القصة من بغداد، "
            "مدينة العلم والحضارة."
        ),
        "voice": {
            "voice_id": "cedar",
            "speed": 1.0,
        },
        "segmentation": {
            "max_words": 20,
        },
        "tts": {
            "provider_id": (
                "openai-speech-v1"
            ),
            "model": (
                "gpt-4o-mini-tts"
            ),
            "instructions": (
                "اقرأ بالعربية الفصحى، "
                "بصوت وثائقي هادئ وواضح، "
                "ومن دون مبالغة مسرحية."
            ),
            "response_format": "wav",
            "sample_rate": 24000,
            "pause_ms": 160,
        },
        "output": {
            "audio": (
                "working/voice-v1/"
                "openai-live-smoke-test.wav"
            ),
            "report": (
                "manifests/"
                "openai-live-smoke-test-report.json"
            ),
        },
    }

    request_path = (
        PROJECT_ROOT
        / "manifests"
        / "openai-live-smoke-test-request.json"
    )

    atomic_write_json(
        request_path,
        request,
    )

    registry = TTSProviderRegistry()
    registry.register(
        OpenAISpeechProvider()
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
            OPENAI_SPEECH_RETRYABLE_ERRORS
        ),
    )

    result = orchestrator.synthesize(
        request=request,
        project_root=PROJECT_ROOT,
    )

    print(
        json.dumps(
            {
                "status": result.status,
                "provider_id": (
                    result.provider_id
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

    if result.status != "VALID":
        raise RuntimeError(
            "OPENAI_LIVE_TTS_INVALID"
        )

    if result.segment_count != 1:
        raise RuntimeError(
            "OPENAI_LIVE_SMOKE_TEST_MUST_USE_ONE_SEGMENT"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())