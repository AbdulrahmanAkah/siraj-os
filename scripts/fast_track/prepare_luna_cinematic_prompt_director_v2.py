from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.application.luna_cinematic_prompt_director_v2 import (
    prepare_episode_prompt_plan,
)


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main() -> int:
    _utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument(
        "--episode",
        default="episode-001-adam",
    )
    args = parser.parse_args()
    result = prepare_episode_prompt_plan(
        Path(args.repo),
        args.episode,
    )
    print(
        json.dumps(
            {
                "release": result["release"],
                "status": result["status"],
                "episode_id": result["episode_id"],
                "prompt_item_count": result["prompt_item_count"],
                "batch_count": result["batch_count"],
                "maximum_luna_requests": result[
                    "maximum_luna_requests"
                ],
                "estimated_cost_usd": result[
                    "estimated_cost_usd"
                ],
                "maximum_authorized_usd": result[
                    "maximum_authorized_usd"
                ],
                "provider_requests": 0,
                "paid_provider_requests": 0,
                "full_episode_production_authorized": False,
                "next_stage": result["next_stage"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
