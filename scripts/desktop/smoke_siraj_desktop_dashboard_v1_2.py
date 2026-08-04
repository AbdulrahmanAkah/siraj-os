from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QListWidget, QScrollArea


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    sys.path.insert(0, str(repo_root))

    from src.presentation.desktop.main_window import SirajDesktopWindow

    app = QApplication.instance() or QApplication(["siraj-v1-2-smoke"])
    window = SirajDesktopWindow(repo_root)
    window.resize(1366, 768)
    window.show()
    for _ in range(8):
        app.processEvents()

    scroll = window.findChild(QScrollArea, "workspaceScroll")
    require(scroll is not None, "WORKSPACE_SCROLL_MISSING")
    require(
        scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        "WORKSPACE_HORIZONTAL_SCROLL_POLICY_CHANGED",
    )
    require(scroll.horizontalScrollBar().maximum() == 0, "HORIZONTAL_OVERFLOW_AT_1366X768")

    hero = window.findChild(QFrame, "projectHero")
    require(hero is not None and hero.isVisible(), "COMPACT_PROJECT_HERO_NOT_VISIBLE")
    require(hero.height() >= 90, f"COMPACT_PROJECT_HERO_TOO_SMALL:{hero.height()}")

    preview_panel = window.findChild(QFrame, "previewPanel")
    require(preview_panel is not None and preview_panel.isVisible(), "PREVIEW_PANEL_NOT_VISIBLE")
    require(preview_panel.height() >= 285, f"PREVIEW_PANEL_COLLAPSED:{preview_panel.height()}")

    preview = window.findChild(QLabel, "__never__")
    preview = window.findChild(type(window.preview), "previewCanvas")
    require(preview is not None and preview.isVisible(), "PREVIEW_CANVAS_NOT_VISIBLE")
    require(preview.height() >= 169, f"PREVIEW_CANVAS_COLLAPSED:{preview.height()}")
    ratio = preview.width() / max(1, preview.height())
    require(1.50 <= ratio <= 2.05, f"PREVIEW_ASPECT_OUT_OF_RANGE:{ratio:.3f}")

    outputs = window.findChild(QListWidget, "outputsList")
    require(outputs is not None, "OUTPUT_LIST_MISSING")
    if outputs.count() and outputs.itemWidget(outputs.item(0)) is not None:
        row = outputs.itemWidget(outputs.item(0))
        file_label = row.findChild(QLabel, "fileName")
        require(file_label is not None, "OUTPUT_FILENAME_LABEL_MISSING")
        require("/" not in file_label.text() and "\\" not in file_label.text(), "OUTPUT_SHOWS_FULL_PATH")
        require(bool(file_label.toolTip()), "OUTPUT_FULL_PATH_TOOLTIP_MISSING")

    activities = window.findChild(QListWidget, "activitiesList")
    require(activities is not None, "ACTIVITY_LIST_MISSING")
    if activities.count() and activities.itemWidget(activities.item(0)) is not None:
        row = activities.itemWidget(activities.item(0))
        label = row.findChild(QLabel, "activityText")
        require(label is not None and label.wordWrap(), "ACTIVITY_WORD_WRAP_MISSING")

    output_root.mkdir(parents=True, exist_ok=True)
    screenshot = output_root / "siraj-desktop-dashboard-v1-2-headless.png"
    window.grab().save(str(screenshot))
    result = {
        "status": "PASS_SIRAJ_DESKTOP_DASHBOARD_V1_2_VISUAL_SMOKE",
        "viewport": "1366x768",
        "horizontal_scroll_maximum": scroll.horizontalScrollBar().maximum(),
        "hero_height": hero.height(),
        "preview_panel_height": preview_panel.height(),
        "preview_width": preview.width(),
        "preview_height": preview.height(),
        "preview_ratio": round(ratio, 4),
        "screenshot": str(screenshot),
    }
    report = output_root / "siraj-desktop-dashboard-v1-2-visual-smoke.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print("STATUS=" + result["status"])
    print("VIEWPORT=1366x768")
    print("HORIZONTAL_SCROLL_MAXIMUM=0")
    print("HERO_HEIGHT=" + str(hero.height()))
    print("PREVIEW_PANEL_HEIGHT=" + str(preview_panel.height()))
    print("PREVIEW_CANVAS=" + f"{preview.width()}x{preview.height()}")
    print("SCREENSHOT=" + str(screenshot))
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
