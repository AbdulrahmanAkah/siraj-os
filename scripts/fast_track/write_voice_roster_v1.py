from __future__ import annotations

from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

PROJECT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project"
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from src.application.local_video_production.voice_provider_v1 import (
    atomic_write_json,
)
from src.application.local_video_production.voice_roster_v1 import (
    voice_roster_to_dict,
)


def main() -> int:
    output_path = (
        PROJECT_ROOT
        / "manifests"
        / "production-voice-roster-v1.json"
    )

    atomic_write_json(
        output_path,
        voice_roster_to_dict(),
    )

    print(
        "PRODUCTION_VOICE_ROSTER_MANIFEST_WRITTEN"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())