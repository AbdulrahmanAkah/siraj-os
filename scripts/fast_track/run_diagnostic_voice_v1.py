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


from src.application.local_video_production.diagnostic_voice_provider_v1 import (
    DiagnosticToneVoiceProvider,
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
            "episode-render-v2-diagnostic-voice"
        ),
        "episode_id": (
            "episode-render-v2-prototype"
        ),
        "language": "ar",
        "text": (
            "بدأت القصة منذ زمن بعيد، "
            "حين كانت بغداد مركزا للعلم والحضارة. "
            "وعبر الأنهار والطرق القديمة، "
            "انتقلت المعرفة بين المدن والأجيال."
        ),
        "voice": {
            "voice_id": "diagnostic-tone",
            "speed": 1.0,
        },
        "pronunciation_map": {
            "بغداد": "بغداد",
        },
        "segmentation": {
            "max_words": 10,
        },
        "provider_config": {
            "sample_rate": 48000,
            "pause_ms": 180,
            "amplitude": 0.12,
        },
        "output": {
            "audio": (
                "working/voice-v1/"
                "diagnostic-narration.wav"
            ),
            "report": (
                "manifests/"
                "diagnostic-voice-v1-report.json"
            ),
        },
    }

    request_path = (
        PROJECT_ROOT
        / "manifests"
        / "diagnostic-voice-v1-request.json"
    )

    atomic_write_json(
        request_path,
        request,
    )

    provider = (
        DiagnosticToneVoiceProvider()
    )

    result = provider.synthesize(
        request=request,
        project_root=PROJECT_ROOT,
    )

    print(
        json.dumps(
            {
                "status": result.status,
                "provider": result.provider,
                "audio": result.output_path,
                "report": result.report_path,
                "segment_count": (
                    result.segment_count
                ),
                "sha256": (
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
            "DIAGNOSTIC_VOICE_LIVE_INVALID"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())