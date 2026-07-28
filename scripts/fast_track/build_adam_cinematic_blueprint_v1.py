from __future__ import annotations

import argparse
from pathlib import Path
import sys


# Direct execution sets sys.path[0] to scripts/fast_track rather than the
# repository root. Bootstrap the checkout root before importing src.* so this
# entry point works from temporary clones and arbitrary current directories.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
repository_root_text = str(REPOSITORY_ROOT)
if repository_root_text not in sys.path:
    sys.path.insert(0, repository_root_text)


from src.application.storyboard_runtime.editorial_bridge import (
    EditorialStoryboardBridge,
    write_blueprint,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Adam episode editorial cinematic blueprint offline."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Siraj repository root (default: current directory).",
    )
    parser.add_argument(
        "--output",
        default=(
            "projects/episode-001-adam/cinematic/"
            "editorial-cinematic-blueprint-v1.json"
        ),
        help="Output path relative to the repository root.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    episode_root = repo_root / "projects/episode-001-adam"
    profile = episode_root / "cinematic/storyboard-profile-v1.json"
    output = repo_root / args.output

    blueprint = EditorialStoryboardBridge().build_from_project(
        episode_root,
        profile,
    )
    write_blueprint(output, blueprint)

    print("STATUS=PASS_OFFLINE_EDITORIAL_CINEMATIC_BLUEPRINT")
    print(f"OUTPUT={output}")
    print(f"BRIDGE_ID={blueprint.bridge_id}")
    print(f"STORYBOARD_ID={blueprint.storyboard.storyboard_id}")
    print(f"FRAME_COUNT={blueprint.storyboard.frame_count}")
    print("EPISODE_TARGET_SECONDS=1320")
    print("GENERATED_VIDEO_PREALLOCATION_SECONDS=0")
    print(f"EVIDENCE_GATE_STATUS={blueprint.evidence_gate_status}")
    print(f"RUNWARE_EXECUTION_STATUS={blueprint.compiled_episode.plan.runware_execution_status}")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
