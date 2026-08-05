from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.structural_montage_final_render_v1 import (
    run_structural_montage_final_render,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run_structural_montage_final_render(args.repo_root)
    print(
        json.dumps(
            {
                "status": result.status,
                "episode_id": result.episode_id,
                "rendered_shot_count": result.rendered_shot_count,
                "reused_shot_count": result.reused_shot_count,
                "duration_seconds": result.duration_seconds,
                "final_master_path": str(result.final_master_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
