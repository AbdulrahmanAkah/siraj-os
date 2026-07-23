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


from src.application.local_video_production.edge_speech_provider_v1 import (
    EdgeSpeechProvider,
)
from src.application.local_video_production.production_tts_v1 import (
    TTSSegmentRequest,
    file_sha256,
    inspect_pcm_wav,
)
from src.application.local_video_production.voice_provider_v1 import (
    atomic_write_json,
)


SAMPLE_TEXT = (
    "بدأت القصة من بغداد، مدينة العلم والحضارة، "
    "حيث التقت طرق التجارة بأصوات العلماء والرحالة."
)

VOICE_IDS = (
    "ar-SA-HamedNeural",
    "ar-AE-HamdanNeural",
    "ar-IQ-BasselNeural",
    "ar-JO-TaimNeural",
    "ar-KW-FahedNeural",
    "ar-QA-MoazNeural",
    "ar-BH-AliNeural",
    "ar-OM-AbdullahNeural",
    "ar-EG-ShakirNeural",
)


def main() -> int:
    provider = EdgeSpeechProvider()

    output_root = (
        PROJECT_ROOT
        / "working"
        / "voice-samples"
        / "edge-arabic-v1"
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    results: list[dict] = []

    for index, voice_id in enumerate(
        VOICE_IDS,
        start=1,
    ):
        output_path = (
            output_root
            / f"{index:02d}-{voice_id}.wav"
        )

        request = TTSSegmentRequest(
            segment_id=f"sample-{index:02d}",
            text=SAMPLE_TEXT,
            language="ar",
            model="edge-tts",
            voice_id=voice_id,
            speed=0.96,
            instructions=None,
            response_format="wav",
            sample_rate=24000,
        )

        provider.synthesize_segment(
            request,
            output_path,
        )

        info = inspect_pcm_wav(
            output_path
        )

        results.append(
            {
                "index": index,
                "voice_id": voice_id,
                "output": str(output_path),
                "duration_ms": (
                    info["duration_ms"]
                ),
                "sample_rate": (
                    info["sample_rate"]
                ),
                "sha256": file_sha256(
                    output_path
                ),
            }
        )

    manifest_path = (
        PROJECT_ROOT
        / "manifests"
        / "edge-arabic-voice-samples-v1.json"
    )

    manifest = {
        "schema_version": (
            "siraj-edge-arabic-voice-samples-v1"
        ),
        "status": "VALID",
        "sample_text": SAMPLE_TEXT,
        "voice_count": len(results),
        "samples": results,
    }

    atomic_write_json(
        manifest_path,
        manifest,
    )

    print(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())