from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from src.application.consolidated_episode_production_controller_v2 import (
    inspect_consolidated_production_plan,
    run_consolidated_production_to_human_gate,
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
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    execute = sub.add_parser("run")
    execute.add_argument("--authorized-maximum-usd", type=float, required=True)
    args = parser.parse_args()
    repo = Path(args.repo)
    if args.command == "status":
        result = inspect_consolidated_production_plan(repo).as_dict()
    else:
        result = {
            "status": "BLOCKED",
            "reason": "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY",
            "supported_launcher": "python -m src.presentation.desktop",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 4 if args.command == "run" else 0


if __name__ == "__main__":
    raise SystemExit(main())
