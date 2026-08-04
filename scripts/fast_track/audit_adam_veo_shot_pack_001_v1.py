from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()

    sys.path.insert(0, str(repo_root))
    from src.application.storyboard_runtime.veo_shot_package_v1 import (
        validate_repository,
    )

    result = validate_repository(repo_root)
    output_root.mkdir(parents=True, exist_ok=True)
    report = output_root / "adam-veo-shot-pack-001-v1-audit.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for key, value in result.items():
        print(f"{key.upper()}={value}")
    print("REPORT=" + str(report))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
