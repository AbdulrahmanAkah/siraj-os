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
    OpenAISpeechProvider,
)
from src.application.local_video_production.production_tts_v1 import (
    TTSProviderRegistry,
    build_production_tts_plan,
)
from src.application.local_video_production.voice_provider_v1 import (
    VOICE_REQUEST_SCHEMA_V1,
    atomic_write_json,
)


def main() -> int:
    request = {
        "schema_version": (
            VOICE_REQUEST_SCHEMA_V1
        ),
        "request_id": (
            "openai-production-tts-dry-run-v1"
        ),
        "episode_id": (
            "episode-render-v2-production-tts"
        ),
        "language": "ar",
        "text": (
            "بدأت القصة منذ زمن بعيد، "
            "حين كانت بغداد مركزا للعلم والحضارة. "
            "وعبر الأنهار والطرق القديمة، "
            "انتقلت المعرفة بين المدن والأجيال."
        ),
        "voice": {
            "voice_id": "cedar",
            "speed": 1.0,
        },
        "pronunciation_map": {
            "بغداد": "بغداد",
        },
        "segmentation": {
            "max_words": 10,
        },
        "tts": {
            "provider_id": (
                "openai-speech-v1"
            ),
            "model": (
                "gpt-4o-mini-tts"
            ),
            "instructions": (
                "اقرأ بصوت وثائقي عربي هادئ، "
                "واضح، ورصين، مع وقفات طبيعية."
            ),
            "response_format": "wav",
            "sample_rate": 24000,
            "pause_ms": 180,
        },
        "output": {
            "audio": (
                "working/voice-v1/"
                "openai-production-narration.wav"
            ),
            "report": (
                "manifests/"
                "openai-production-tts-report.json"
            ),
        },
    }

    request_path = (
        PROJECT_ROOT
        / "manifests"
        / "openai-production-tts-request.json"
    )

    plan_path = (
        PROJECT_ROOT
        / "manifests"
        / "openai-production-tts-dry-run.json"
    )

    atomic_write_json(
        request_path,
        request,
    )

    registry = TTSProviderRegistry()

    registry.register(
        OpenAISpeechProvider()
    )

    plan = build_production_tts_plan(
        request=request,
        project_root=PROJECT_ROOT,
        registry=registry,
    )

    atomic_write_json(
        plan_path,
        plan,
    )

    print(
        json.dumps(
            plan,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    if plan["status"] != "VALID":
        raise RuntimeError(
            "OPENAI_TTS_DRY_RUN_INVALID"
        )

    if plan["external_api_called"]:
        raise RuntimeError(
            "OPENAI_TTS_DRY_RUN_CALLED_API"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())