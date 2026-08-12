from __future__ import annotations

import argparse
from pathlib import Path

from src.presentation.desktop.production_studio_v5_4_4 import (
    launch_production_studio,
)


def main():
    raise SystemExit(
        "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY: "
        "legacy V5.4.4 launcher is non-authoritative; use python -m src.presentation.desktop"
    )


if __name__ == "__main__":
    main()
