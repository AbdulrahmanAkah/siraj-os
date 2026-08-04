from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QScrollArea, QTableWidget
    except ImportError:
        print("STATUS=SKIP_SIRAJ_DESKTOP_DASHBOARD_V1_1_GUI_SMOKE")
        print("REASON=PYSIDE6_NOT_INSTALLED")
        return 0

    repo_root = args.repo_root.resolve()
    sys.path.insert(0, str(repo_root))
    from src.presentation.desktop.main_window import SirajDesktopWindow

    app = QApplication.instance() or QApplication(["siraj-v1-1-smoke"])
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    window = SirajDesktopWindow(repo_root)
    window.resize(1366, 768)
    window.show()
    app.processEvents()

    scroll_areas = window.findChildren(QScrollArea)
    tables = window.findChildren(QTableWidget)
    for area in scroll_areas:
        if area.horizontalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
            raise RuntimeError("HORIZONTAL_SCROLL_AREA_POLICY_NOT_BLOCKED")
    for table in tables:
        if table.horizontalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
            raise RuntimeError("HORIZONTAL_TABLE_POLICY_NOT_BLOCKED")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    screenshot = output_root / "siraj-desktop-dashboard-v1-1-offscreen-1366x768.png"
    window.grab().save(str(screenshot))

    print("STATUS=PASS_SIRAJ_DESKTOP_DASHBOARD_V1_1_GUI_SMOKE")
    print("WINDOW_SIZE=1366x768")
    print("SCROLL_AREA_COUNT=" + str(len(scroll_areas)))
    print("TABLE_COUNT=" + str(len(tables)))
    print("HORIZONTAL_SCROLL_POLICIES=BLOCKED")
    print("SCREENSHOT=" + str(screenshot))
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
