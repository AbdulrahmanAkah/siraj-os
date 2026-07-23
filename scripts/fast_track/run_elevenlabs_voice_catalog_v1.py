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


from src.application.local_video_production.elevenlabs_voice_catalog_v1 import (
    ELEVENLABS_VOICE_CATALOG_SCHEMA_V1,
    fetch_voice_catalog,
    voice_candidate_to_dict,
)
from src.application.local_video_production.voice_provider_v1 import (
    atomic_write_json,
)


def main() -> int:
    candidates = fetch_voice_catalog(
        page_size=100,
    )

    if not candidates:
        raise RuntimeError(
            "ELEVENLABS_NO_VOICES_AVAILABLE"
        )

    recommended = [
        item
        for item in candidates
        if item.available_for_free
    ][:10]

    if not recommended:
        recommended = candidates[:10]

    output_path = (
        PROJECT_ROOT
        / "manifests"
        / "elevenlabs-voice-catalog-v1.json"
    )

    result = {
        "schema_version": (
            ELEVENLABS_VOICE_CATALOG_SCHEMA_V1
        ),
        "status": "VALID",
        "total_voice_count": len(
            candidates
        ),
        "recommended_voice_count": len(
            recommended
        ),
        "external_api_called": True,
        "audio_generated": False,
        "recommended_voices": [
            voice_candidate_to_dict(
                item
            )
            for item in recommended
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