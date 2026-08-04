from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Prefer the host Windows font directory when the offscreen Qt plugin can
# use it, but keep all visual assertions independent of text rendering.
if os.name == "nt":
    windows_fonts = Path(
        os.environ.get("WINDIR", r"C:\\Windows")
    ) / "Fonts"
    if windows_fonts.is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", str(windows_fonts))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QScrollArea,
    QTabWidget,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def effective_visible_rect(widget, viewport) -> QRect:
    global_top_left = widget.mapToGlobal(QPoint(0, 0))
    viewport_top_left = viewport.mapFromGlobal(global_top_left)
    candidate = QRect(viewport_top_left, widget.size())
    return candidate.intersected(viewport.rect())


def image_pixel_signature(image: QImage) -> dict[str, int]:
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    width = image.width()
    height = image.height()
    require(width > 0 and height > 0, "EMPTY_WIDGET_GRAB")

    step_x = max(1, width // 48)
    step_y = max(1, height // 32)
    buckets: set[tuple[int, int, int]] = set()
    gold_like = 0
    dark_like = 0
    sampled = 0
    luminance_min = 255
    luminance_max = 0

    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            color = image.pixelColor(x, y)
            red, green, blue = color.red(), color.green(), color.blue()
            buckets.add((red // 12, green // 12, blue // 12))
            sampled += 1
            luminance = round(
                0.2126 * red + 0.7152 * green + 0.0722 * blue
            )
            luminance_min = min(luminance_min, luminance)
            luminance_max = max(luminance_max, luminance)
            if red >= 145 and green >= 85 and blue <= 90:
                gold_like += 1
            if red <= 45 and green <= 65 and blue <= 80:
                dark_like += 1

    return {
        "sampled": sampled,
        "diversity": len(buckets),
        "gold_like": gold_like,
        "dark_like": dark_like,
        "luminance_span": luminance_max - luminance_min,
    }


def pixel_signature(widget) -> dict[str, int]:
    return image_pixel_signature(widget.grab().toImage())


def visible_pixel_signature(widget, viewport) -> dict[str, int]:
    visible = effective_visible_rect(widget, viewport)
    require(
        visible.width() > 0 and visible.height() > 0,
        "EMPTY_EFFECTIVE_VISIBLE_PIXEL_REGION",
    )
    # Grab the viewport crop, not the theoretical full widget. This proves the
    # pixels are actually visible to the user at the tested window size.
    return image_pixel_signature(viewport.grab(visible).toImage())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    sys.path.insert(0, str(repo_root))

    from src.presentation.desktop.main_window import SirajDesktopWindow

    app = QApplication.instance() or QApplication(["siraj-v1-3-smoke"])
    window = SirajDesktopWindow(repo_root)
    window.resize(1366, 768)
    window.show()
    for _ in range(16):
        app.processEvents()

    main_scroll = window.findChild(QScrollArea, "mainColumnScroll")
    utility_scroll = window.findChild(QScrollArea, "utilityColumnScroll")
    require(main_scroll is not None, "MAIN_COLUMN_SCROLL_MISSING")
    require(utility_scroll is not None, "UTILITY_COLUMN_SCROLL_MISSING")
    require(main_scroll is not utility_scroll, "COLUMN_SCROLLS_NOT_INDEPENDENT")

    for name, scroll in (
        ("MAIN", main_scroll),
        ("UTILITY", utility_scroll),
    ):
        require(
            scroll.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            f"{name}_HORIZONTAL_SCROLL_POLICY_CHANGED",
        )
        require(
            scroll.horizontalScrollBar().maximum() == 0,
            f"{name}_HORIZONTAL_OVERFLOW_AT_1366X768",
        )
        require(
            scroll.verticalScrollBar().value() == 0,
            f"{name}_INITIAL_SCROLL_POSITION_NOT_TOP",
        )

    hero = window.findChild(QFrame, "projectHero")
    require(hero is not None and hero.isVisible(), "COMPACT_PROJECT_HERO_NOT_VISIBLE")
    require(hero.height() >= 90, f"COMPACT_PROJECT_HERO_TOO_SMALL:{hero.height()}")

    queue_panel = window.findChild(QFrame, "queuePanel")
    queue_tabs = window.findChild(QTabWidget, "episodeQueueTabs")
    require(queue_panel is not None, "QUEUE_PANEL_MISSING")
    require(queue_tabs is not None, "QUEUE_TABS_MISSING")

    queue_visible = effective_visible_rect(
        queue_panel,
        main_scroll.viewport(),
    )
    tabs_visible = effective_visible_rect(
        queue_tabs,
        main_scroll.viewport(),
    )
    require(
        queue_visible.height() >= 225,
        "MAIN_QUEUE_EFFECTIVE_VISIBILITY:"
        f"{queue_visible.width()}x{queue_visible.height()}",
    )
    require(
        tabs_visible.height() >= 165,
        "QUEUE_TABS_EFFECTIVE_VISIBILITY:"
        f"{tabs_visible.width()}x{tabs_visible.height()}",
    )
    require(window.work_table.rowCount() >= 1, "WORK_QUEUE_ROW_MISSING")
    require(window.work_table.isVisible(), "WORK_QUEUE_TABLE_NOT_VISIBLE")
    require(queue_tabs.currentIndex() == 1, "WORK_QUEUE_TAB_NOT_ACTIVE")

    preview_panel = window.findChild(QFrame, "previewPanel")
    preview_title = window.findChild(QLabel, "previewTitle")
    preview_status = window.findChild(QFrame, "previewStatus")
    preview = window.preview

    require(preview_panel is not None, "PREVIEW_PANEL_MISSING")
    require(preview_title is not None, "PREVIEW_TITLE_MISSING")
    require(preview_status is not None, "PREVIEW_STATUS_MISSING")

    panel_visible = effective_visible_rect(
        preview_panel,
        utility_scroll.viewport(),
    )
    title_visible = effective_visible_rect(
        preview_title,
        utility_scroll.viewport(),
    )
    status_visible = effective_visible_rect(
        preview_status,
        utility_scroll.viewport(),
    )
    preview_visible = effective_visible_rect(
        preview,
        utility_scroll.viewport(),
    )

    require(
        panel_visible.height() >= 305,
        "PREVIEW_EFFECTIVE_VISIBILITY:"
        f"{panel_visible.width()}x{panel_visible.height()}",
    )
    require(
        title_visible.height() >= 18,
        f"PREVIEW_TITLE_NOT_EFFECTIVELY_VISIBLE:{title_visible.height()}",
    )
    require(
        status_visible.height() >= 18,
        f"PREVIEW_STATUS_NOT_EFFECTIVELY_VISIBLE:{status_visible.height()}",
    )
    require(
        preview_visible.height() >= 169,
        "PREVIEW_CANVAS_EFFECTIVE_VISIBILITY:"
        f"{preview_visible.width()}x{preview_visible.height()}",
    )

    ratio = preview.width() / max(1, preview.height())
    require(
        1.50 <= ratio <= 2.05,
        f"PREVIEW_ASPECT_OUT_OF_RANGE:{ratio:.3f}",
    )

    preview_pixels = visible_pixel_signature(
        preview,
        utility_scroll.viewport(),
    )
    require(
        preview_pixels["diversity"] >= 18,
        "PREVIEW_PIXEL_DIVERSITY:"
        f"{preview_pixels['diversity']}",
    )
    require(
        preview_pixels["gold_like"] >= 3,
        "PREVIEW_GOLD_ACCENT_PIXELS_MISSING",
    )
    require(
        preview_pixels["dark_like"] >= 20,
        "PREVIEW_DARK_SCENE_PIXELS_MISSING",
    )

    queue_pixels = visible_pixel_signature(
        queue_panel,
        main_scroll.viewport(),
    )
    # Text glyph diversity is not a valid requirement in Qt offscreen
    # mode because the plugin may not load a font database. Validate the
    # painted structure instead: multiple color buckets, the gold border,
    # the dark surface, and a meaningful luminance span.
    require(
        queue_pixels["diversity"] >= 4,
        "QUEUE_PIXEL_DIVERSITY:"
        f"{queue_pixels['diversity']}",
    )
    require(
        queue_pixels["gold_like"] >= 2,
        "QUEUE_GOLD_BORDER_PIXELS_MISSING",
    )
    require(
        queue_pixels["dark_like"] >= 20,
        "QUEUE_DARK_SURFACE_PIXELS_MISSING",
    )
    require(
        queue_pixels["luminance_span"] >= 40,
        "QUEUE_PIXEL_LUMINANCE_SPAN:"
        f"{queue_pixels['luminance_span']}",
    )

    output_root.mkdir(parents=True, exist_ok=True)
    screenshot = (
        output_root / "siraj-desktop-dashboard-v1-3-headless.png"
    )
    window.grab().save(str(screenshot))

    result = {
        "status": "PASS_SIRAJ_DESKTOP_DASHBOARD_V1_3_VISUAL_SMOKE",
        "viewport": "1366x768",
        "main_horizontal_scroll_maximum":
            main_scroll.horizontalScrollBar().maximum(),
        "utility_horizontal_scroll_maximum":
            utility_scroll.horizontalScrollBar().maximum(),
        "main_queue_visible_geometry": {
            "x": queue_visible.x(),
            "y": queue_visible.y(),
            "width": queue_visible.width(),
            "height": queue_visible.height(),
        },
        "preview_panel_visible_geometry": {
            "x": panel_visible.x(),
            "y": panel_visible.y(),
            "width": panel_visible.width(),
            "height": panel_visible.height(),
        },
        "preview_canvas_visible_geometry": {
            "x": preview_visible.x(),
            "y": preview_visible.y(),
            "width": preview_visible.width(),
            "height": preview_visible.height(),
        },
        "preview_ratio": round(ratio, 4),
        "preview_pixels": preview_pixels,
        "queue_pixels": queue_pixels,
        "font_rendering_dependency": "NOT_REQUIRED",
        "queue_pixel_assertion": (
            "VISIBLE_DARK_GOLD_LUMINANCE_STRUCTURE"
        ),
        "screenshot": str(screenshot),
    }
    report = (
        output_root / "siraj-desktop-dashboard-v1-3-visual-smoke.json"
    )
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print("STATUS=" + result["status"])
    print("VIEWPORT=1366x768")
    print("MAIN_HORIZONTAL_SCROLL_MAXIMUM=0")
    print("UTILITY_HORIZONTAL_SCROLL_MAXIMUM=0")
    print(
        "MAIN_QUEUE_VISIBLE="
        f"{queue_visible.width()}x{queue_visible.height()}"
    )
    print(
        "PREVIEW_PANEL_VISIBLE="
        f"{panel_visible.width()}x{panel_visible.height()}"
    )
    print(
        "PREVIEW_CANVAS_VISIBLE="
        f"{preview_visible.width()}x{preview_visible.height()}"
    )
    print(
        "PREVIEW_PIXEL_DIVERSITY="
        + str(preview_pixels["diversity"])
    )
    print(
        "QUEUE_PIXEL_DIVERSITY="
        + str(queue_pixels["diversity"])
    )
    print(
        "QUEUE_PIXEL_LUMINANCE_SPAN="
        + str(queue_pixels["luminance_span"])
    )
    print("FONT_RENDERING_DEPENDENCY=NOT_REQUIRED")
    print("SCREENSHOT=" + str(screenshot))

    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
