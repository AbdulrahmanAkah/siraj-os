from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.application.end_to_end_production_v1 import (
    inspect_end_to_end_plan,
    run_to_next_human_gate,
)
from src.application.youtube_publish_handoff_v1 import (
    complete_youtube_publish_handoff,
    load_youtube_handoff_status,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    run = subparsers.add_parser("run")
    run.add_argument("--confirm-media-max-usd", type=float)
    subparsers.add_parser("handoff")
    subparsers.add_parser("handoff-status")
    args = parser.parse_args()

    if args.command == "status":
        payload = inspect_end_to_end_plan(args.repo_root).as_dict()
    elif args.command == "handoff":
        payload = complete_youtube_publish_handoff(args.repo_root).as_dict()
    elif args.command == "handoff-status":
        payload = load_youtube_handoff_status(args.repo_root)
    else:
        result = run_to_next_human_gate(
            args.repo_root,
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            runware_api_key=os.environ.get("RUNWARE_API_KEY", ""),
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
            confirmed_media_maximum_usd=args.confirm_media_max_usd,
        )
        payload = result.as_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
