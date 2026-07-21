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


from scripts.project_progress.recorder import (
    atomic_write_json,
)
from src.application.local_video_production.episode_render_v2 import (
    EPISODE_RENDER_MANIFEST_V2,
    build_timed_scene_plan,
    validate_episode_render_manifest_v2,
)


def main() -> int:
    source_manifest_path = (
        PROJECT_ROOT
        / "manifests"
        / "quality-gate-v4-manifest.json"
    )

    original = json.loads(
        source_manifest_path.read_text(
            encoding="utf-8-sig"
        )
    )

    assets = original["assets"][:3]

    if len(assets) != 3:
        raise RuntimeError(
            "THREE_PROTOTYPE_ASSETS_REQUIRED"
        )

    scene_specs = [
        {
            "scene_id": "scene-001",
            "duration_ms": 5_800,
            "visual_asset_path": assets[0]["path"],
            "motion": "PUSH_IN",
            "transition": "FADE",
            "claim_ids": [
                "prototype-claim-001"
            ],
            "source_ids": [
                "prototype-source-001"
            ],
            "visual_policy_refs": [
                "no-prophetic-depiction",
                "environment-only",
            ],
        },
        {
            "scene_id": "scene-002",
            "duration_ms": 7_100,
            "visual_asset_path": assets[1]["path"],
            "motion": "PAN_LEFT_TO_RIGHT",
            "transition": "DISSOLVE",
            "claim_ids": [
                "prototype-claim-002"
            ],
            "source_ids": [
                "prototype-source-002"
            ],
            "visual_policy_refs": [
                "historical-reconstruction",
            ],
        },
        {
            "scene_id": "scene-003",
            "duration_ms": 6_502,
            "visual_asset_path": assets[2]["path"],
            "motion": "PAN_RIGHT_TO_LEFT",
            "transition": "DIP_TO_BLACK",
            "claim_ids": [
                "prototype-claim-003"
            ],
            "source_ids": [
                "prototype-source-003"
            ],
            "visual_policy_refs": [
                "architecture-review-required",
            ],
        },
    ]

    timed_scenes = build_timed_scene_plan(
        scene_specs
    )

    manifest = {
        "schema_version": (
            EPISODE_RENDER_MANIFEST_V2
        ),
        "episode_id": (
            "episode-render-v2-prototype"
        ),
        "title": (
            "Episode Render Manifest v2 Prototype"
        ),
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "start_ms": scene.start_ms,
                "end_ms": scene.end_ms,
                "duration_ms": scene.duration_ms,
                "visual_asset_path": (
                    scene.visual_asset_path
                ),
                "motion": scene.motion,
                "transition": scene.transition,
                "claim_ids": list(
                    scene.claim_ids
                ),
                "source_ids": list(
                    scene.source_ids
                ),
                "visual_policy_refs": list(
                    scene.visual_policy_refs
                ),
            }
            for scene in timed_scenes
        ],
        "audio_layers": [
            {
                "layer_id": "narration",
                "role": "NARRATION",
                "path": (
                    "working/production-v4/"
                    "quality-gate-mix.wav"
                ),
                "start_ms": 0,
                "gain_db": 0,
            },
            {
                "layer_id": "ambient-river",
                "role": "AMBIENCE",
                "path": (
                    "working/production-v4/"
                    "quality-gate-sfx/"
                    "river-ambience.wav"
                ),
                "start_ms": 250,
                "gain_db": -30,
            },
            {
                "layer_id": "transition-effect",
                "role": "EFFECT",
                "path": (
                    "working/production-v4/"
                    "quality-gate-sfx/"
                    "historical-transition.wav"
                ),
                "start_ms": 6_000,
                "gain_db": -30,
            },
        ],
        "subtitles": {
            "mode": "SIDECAR",
            "path": (
                "working/production-v4/"
                "quality-gate-v4.srt"
            ),
            "language": "ar",
            "direction": "RTL",
        },
        "output": {
            "video": (
                "exports/"
                "episode-render-v2-prototype.mp4"
            ),
            "report": (
                "manifests/"
                "episode-render-v2-prototype-report.json"
            ),
        },
        "production_final": False,
        "human_review_required": True,
    }

    validate_episode_render_manifest_v2(
        manifest
    )

    target = (
        PROJECT_ROOT
        / "manifests"
        / "episode-render-v2-prototype.json"
    )

    atomic_write_json(
        target,
        manifest,
    )

    print(str(target))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())