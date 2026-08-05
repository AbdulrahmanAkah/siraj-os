from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.episode_001_pipeline_adoption_v1 import (
    adopt_episode_001_for_pipeline,
    inspect_episode_001_adoption,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "command",
        choices=("status", "adopt"),
        nargs="?",
        default="status",
    )
    args = parser.parse_args()
    if args.command == "adopt":
        payload = adopt_episode_001_for_pipeline(args.repo_root).as_dict()
    else:
        payload = inspect_episode_001_adoption(args.repo_root).as_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
