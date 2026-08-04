from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .repository import find_repo_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the SIRAJ desktop dashboard.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Absolute path to the siraj-os repository.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is required for the SIRAJ desktop interface.\n"
            "Install it with:\n"
            "  python -m pip install -e \".[desktop]\"",
            file=sys.stderr,
        )
        return 5

    from .main_window import SirajDesktopWindow

    args = _parser().parse_args(argv)
    repo_root = (
        args.repo_root.resolve()
        if args.repo_root is not None
        else find_repo_root()
    )
    if not repo_root.is_dir():
        print(f"Repository not found: {repo_root}", file=sys.stderr)
        return 2

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    application = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    application.setApplicationName("SIRAJ Desktop")
    application.setOrganizationName("SIRAJ")
    application.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    application.setFont(QFont("Segoe UI", 10))

    window = SirajDesktopWindow(repo_root)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
