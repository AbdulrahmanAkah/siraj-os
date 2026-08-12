from __future__ import annotations

import argparse
from pathlib import Path
from src.presentation.desktop.production_studio_v6_0_1 import (
    launch_production_studio_v6_0_1,
)


def main():
    raise SystemExit(
        "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY: "
        "legacy V6.0.1 launcher is non-authoritative; use python -m src.presentation.desktop"
    )


if __name__ == "__main__":
    main()
