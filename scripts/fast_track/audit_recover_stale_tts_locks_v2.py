from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.adam_stale_tts_lock_audit_v2 import (
    audit_and_recover,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--episode", default="episode-001-adam")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"NOT_A_GIT_REPOSITORY:{repo}")

    result = audit_and_recover(
        repo,
        episode_id=args.episode,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
