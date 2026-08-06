from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from src.application.luna_cinematic_prompt_director_v2 import (
    execute_authorized_batch,
    finalize_certified_storyboard,
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
    sub = parser.add_subparsers(dest="command", required=True)
    execute = sub.add_parser("execute-batch")
    execute.add_argument("--batch-id", required=True)
    execute.add_argument(
        "--authorized-maximum-usd",
        type=float,
        required=True,
    )
    sub.add_parser("finalize")
    args = parser.parse_args()

    if args.command == "finalize":
        result = finalize_certified_storyboard(
            Path(args.repo),
            episode_id=args.episode,
        )
    else:
        result = execute_authorized_batch(
            Path(args.repo),
            episode_id=args.episode,
            batch_id=args.batch_id,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            confirmed_maximum_usd=args.authorized_maximum_usd,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
