from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.runware_seedream_negative_prompt_recovery_v1 import (
    repair_runtime_seedream_negative_prompt_failure,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = repair_runtime_seedream_negative_prompt_failure(
        args.repo_root
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
