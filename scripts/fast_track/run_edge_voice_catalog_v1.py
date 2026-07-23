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


from src.application.local_video_production.edge_voice_catalog_v1 import (
    EDGE_VOICE_CATALOG_SCHEMA_V1,
    edge_voice_to_dict,
    fetch_arabic_edge_voices,
)
from src.application.local_video_production.voice_provider_v1 import (
    atomic_write_json,
)


def main() -> int:
    voices = fetch_arabic_edge_voices()

    if not voices:
        raise RuntimeError(
            "EDGE_ARABIC_VOICES_NOT_FOUND"
        )

    output_path = (
        PROJECT_ROOT
        / "manifests"
        / "edge-arabic-voice-catalog-v1.json"
    )

    result = {
        "schema_version": (
            EDGE_VOICE_CATALOG_SCHEMA_V1
        ),
        "status": "VALID",
        "voice_count": len(voices),
        "external_service_called": True,
        "audio_generated": False,
        "voices": [
            edge_voice_to_dict(
                voice
            )
            for voice in voices
        ],
    }

    atomic_write_json(
        output_path,
        result,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())