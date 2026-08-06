from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.application.series_production_standard_v2_repair import (
    repair_and_finalize,
)


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main() -> int:
    _configure_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    result = repair_and_finalize(Path(args.repo))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
