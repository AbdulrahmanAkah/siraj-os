"""Build the offline Gemini visual-generation dry run from Storyboard v1."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path: sys.path.insert(0, str(REPOSITORY))

from src.application.local_video_production.visual_generation_director_v1 import build_visual_generation_plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root)
    result = build_visual_generation_plan(
        root / "working" / "storyboard-v1" / "production-storyboard-v1.json",
        root / "working" / "storyboard-v1" / "production-character-bible-v1.json",
        root / "working" / "storyboard-v1" / "production-location-bible-v1.json",
        root / "working" / "visual-provider-v1",
        root / "manifests" / "production-visual-provider-v1.json",
        replace=args.replace,
    )
    print(result.status)
    print(result.manifest_path)
    return 0


if __name__ == "__main__": raise SystemExit(main())
