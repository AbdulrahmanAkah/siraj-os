from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.runtime_state_recovery_v1 import (
    diagnose_runtime_state,
    recover_runtime_state_from_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.repair:
        payload = recover_runtime_state_from_artifacts(
            args.repo_root,
            force=args.force,
        ).as_dict()
    else:
        payload = diagnose_runtime_state(args.repo_root).as_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
