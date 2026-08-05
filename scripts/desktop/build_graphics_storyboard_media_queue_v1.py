from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.graphics_storyboard_media_queue_v1 import (
    integrate_graphics_and_build_media_queue,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = integrate_graphics_and_build_media_queue(args.repo_root)
    print(
        json.dumps(
            {
                "status": result.status,
                "episode_id": result.episode_id,
                "images": result.image_count,
                "videos": result.video_count,
                "graphics": result.graphics_count,
                "tts_segments": result.tts_segment_count,
                "reserved_max_usd": result.reserved_max_usd,
                "projected_total_usd": result.projected_total_usd,
                "tts_voice_selection_required": True,
                "media_queue_path": str(result.media_queue_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
