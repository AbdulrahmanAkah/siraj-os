from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from src.application.adam_visual_replan_v2 import (
    OBSERVED_VIDEO_COST_PER_SECOND_USD,
    build_adam_visual_replan,
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--episode", default="episode-001-adam")
    parser.add_argument(
        "--video-cost-per-second-usd",
        type=float,
        default=OBSERVED_VIDEO_COST_PER_SECOND_USD,
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    episode = repo / "projects" / args.episode
    legacy_storyboard = (
        episode / "cinematic" / "storyboard-and-media-plan-v1.json"
    )
    production_plan = (
        episode / "cinematic" / "episode-production-plan-v2.json"
    )
    if not legacy_storyboard.is_file():
        raise RuntimeError(f"LEGACY_STORYBOARD_NOT_FOUND:{legacy_storyboard}")
    if not production_plan.is_file():
        raise RuntimeError(f"V2_PRODUCTION_PLAN_NOT_FOUND:{production_plan}")

    result = build_adam_visual_replan(
        read_json(legacy_storyboard),
        read_json(production_plan),
        cost_per_second_usd=args.video_cost_per_second_usd,
    )
    storyboard_v2 = (
        episode / "cinematic" / "storyboard-and-media-plan-v2.json"
    )
    summary_path = (
        episode / "orchestration" / "adam-visual-replan-v2-summary.json"
    )
    write_json(storyboard_v2, result.storyboard)
    write_json(production_plan, result.production_plan)
    write_json(summary_path, result.summary)
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
