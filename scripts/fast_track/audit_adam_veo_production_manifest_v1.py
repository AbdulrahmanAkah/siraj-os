from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.storyboard_runtime.veo_production_manifest_v1 import (
    validate_repository,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    result = validate_repository(repo_root)
    output_root = (
        args.output_root.resolve()
        if args.output_root
        else repo_root / "reports" / "adam-veo-production-manifest-v1"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    report = output_root / "adam-veo-production-manifest-v1-audit.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("STATUS=" + result["status"])
    print("POLICY_ID=" + result["policy_id"])
    print("MANIFEST_ID=" + result["manifest_id"])
    print("PRIMARY_VIDEO_MODEL=" + result["primary_video_model"])
    print("SHOT_COUNT=" + str(result["shot_count"]))
    print("EDITORIAL_DURATION_SECONDS=" + str(result["editorial_duration_seconds"]))
    print("NEXT_STAGE=" + result["next_stage"])
    print("REPORT=" + str(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
