from __future__ import annotations

import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from scripts.project_progress.recorder import (
    atomic_write_json,
)


PROJECT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project"
)

ORIGINAL_MANIFEST = (
    PROJECT_ROOT
    / "manifests"
    / "quality-gate-v4-manifest.json"
)

OUTPUT_MANIFEST = (
    PROJECT_ROOT
    / "manifests"
    / "render-adapter-v1-replay.json"
)


def main() -> int:
    original = json.loads(
        ORIGINAL_MANIFEST.read_text(
            encoding="utf-8-sig"
        )
    )

    assets = original["assets"]

    if len(assets) < 3:
        raise RuntimeError(
            "QUALITY_GATE_V4_ASSETS_INCOMPLETE"
        )

    motions = (
        "PAN_RIGHT_TO_LEFT",
        "PUSH_IN",
        "PAN_LEFT_TO_RIGHT",
    )

    manifest = {
        "schema_version": (
            "siraj-local-video-render-manifest-v1"
        ),
        "render_id": (
            "render-adapter-v1-quality-gate-replay"
        ),
        "episode_id": (
            "quality-gate-v4-replay"
        ),
        "video": {
            "width": 1920,
            "height": 1080,
            "fps": 24,
            "codec": "libx264",
            "preset": "medium",
            "transition_ms": 450,
        },
        "audio": {
            "path": (
                "working/production-v4/"
                "quality-gate-mix.wav"
            ),
            "codec": "aac",
            "bitrate": "160k",
            "classification": (
                "FINAL_MIXED_AUDIO"
            ),
        },
        "assets": [
            {
                "asset_id": asset["asset_id"],
                "path": asset["path"],
                "motion": motions[index],
                "source_url": (
                    asset.get("source_url")
                ),
                "sha256": asset.get("sha256"),
            }
            for index, asset in enumerate(
                assets[:3]
            )
        ],
        "subtitles": {
            "path": (
                "working/production-v4/"
                "quality-gate-v4.srt"
            ),
            "mode": "SIDECAR",
        },
        "output": {
            "video": (
                "exports/"
                "render-adapter-v1-replay.mp4"
            ),
            "report": (
                "manifests/"
                "render-adapter-v1-replay-report.json"
            ),
        },
        "production_final": False,
        "purpose": (
            "PROVE_MANIFEST_DRIVEN_RENDER_REUSE"
        ),
    }

    atomic_write_json(
        OUTPUT_MANIFEST,
        manifest,
    )

    print(str(OUTPUT_MANIFEST))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
