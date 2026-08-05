from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.sfx_audio_mix_v1 import run_sfx_audio_mix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run_sfx_audio_mix(args.repo_root)
    print(
        json.dumps(
            {
                "status": result.status,
                "episode_id": result.episode_id,
                "event_count": result.event_count,
                "narration_clip_count": result.narration_clip_count,
                "duration_seconds": result.duration_seconds,
                "master_wav_path": str(result.master_wav_path),
                "master_m4a_path": str(result.master_m4a_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
