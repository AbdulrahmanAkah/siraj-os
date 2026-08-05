from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.application.local_graphics_renderer_v1 import (
    environment_report,
    render_graphic,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    report = environment_report(args.repo_root)
    if args.preflight_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["render_ready"] else 2

    if args.spec is None or args.output is None:
        parser.error("--spec and --output are required for rendering")

    result = render_graphic(
        args.repo_root,
        args.spec,
        args.output,
        keep_frames=args.keep_frames,
        receipt_path=args.receipt,
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "graphic_id": result.graphic_id,
                "shot_id": result.shot_id,
                "graphic_type": result.graphic_type,
                "output_path": str(result.output_path),
                "output_sha256": result.output_sha256,
                "duration_seconds": result.duration_seconds,
                "frame_count": result.frame_count,
                "width": result.width,
                "height": result.height,
                "fps": result.fps,
                "receipt_path": str(result.receipt_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
