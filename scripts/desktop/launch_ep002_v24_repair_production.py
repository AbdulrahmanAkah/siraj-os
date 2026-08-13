from __future__ import annotations

from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.presentation.desktop.ep002_v24_repair_window_v1 import (
    run_v24_repair_desktop,
)

raise SystemExit(run_v24_repair_desktop(REPO))
