from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.adam_tts_preflight_v2 import (
    build_preflight,
    write_preflight_outputs,
)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--episode", default="episode-001-adam")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"NOT_A_GIT_REPOSITORY:{repo}")

    episode = repo / "projects" / args.episode
    script_path = episode / "script/episode-script-v2.json"
    storyboard_path = episode / "cinematic/storyboard-and-media-plan-v2.json"
    if not script_path.is_file():
        raise RuntimeError(f"APPROVED_SCRIPT_NOT_FOUND:{script_path}")
    if not storyboard_path.is_file():
        raise RuntimeError(f"STORYBOARD_NOT_FOUND:{storyboard_path}")

    result = build_preflight(
        repo=repo,
        episode_id=args.episode,
        script=read_json(script_path),
        storyboard=read_json(storyboard_path),
    )
    outputs = write_preflight_outputs(
        repo=repo,
        episode_id=args.episode,
        result=result,
    )

    print(
        json.dumps(
            {
                "release": "SIRAJ_ADAM_TTS_PREFLIGHT_V2",
                "status": result["preflight"]["status"],
                "episode_id": args.episode,
                "credential": result["preflight"]["credential"],
                "voice_cast": result["preflight"]["voice_cast"],
                "script": result["preflight"]["script"],
                "sample": result["preflight"]["sample"],
                "stale_tts_lock_count": result["preflight"][
                    "stale_tts_lock_count"
                ],
                "provider_requests": 0,
                "paid_provider_requests": 0,
                "sample_generation_authorized": False,
                "outputs": outputs,
                "next_stage": result["preflight"]["next_stage"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
