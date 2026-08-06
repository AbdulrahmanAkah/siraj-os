from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.montage_pixel_format_recovery_v1 import (
    recover_montage_pixel_format_failure,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    result = recover_montage_pixel_format_failure(args.repo_root)
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
