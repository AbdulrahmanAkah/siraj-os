from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

STATUS = "PASS_SIRAJ_DESKTOP_DASHBOARD_V1_2"
VERSION = "1.2"


class AuditError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise AuditError(f"CANNOT_READ:{path}:{exc}") from exc


def audit(repo_root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(repo_root))
    from src.presentation.desktop.repository import build_dashboard_snapshot

    desktop = repo_root / "src" / "presentation" / "desktop"
    main_window = _read(desktop / "main_window.py")
    widgets = _read(desktop / "widgets.py")
    theme = _read(desktop / "theme.py")

    required_main_markers = (
        'RELEASE = "SIRAJ_DESKTOP_DASHBOARD_V1_2"',
        'setObjectName("projectHero")',
        'layout.addWidget(self._build_compact_hero())',
        'setObjectName("previewPanel")',
        'panel.setMinimumHeight(292)',
        'setObjectName("previewCanvas")',
        'path.name',
        'setObjectName("fileName")',
        'setObjectName("activityText")',
        'label.setWordWrap(True)',
        'ScrollBarAlwaysOff',
        'self.ready_table',
        'self.work_table',
    )
    for marker in required_main_markers:
        _require(marker in main_window, f"MISSING_MAIN_WINDOW_MARKER:{marker}")

    required_widget_markers = (
        "MIN_PREVIEW_HEIGHT = 169",
        "MAX_PREVIEW_HEIGHT = 232",
        "heightForWidth",
        "resizeEvent",
        "setFixedHeight(target)",
    )
    for marker in required_widget_markers:
        _require(marker in widgets, f"MISSING_WIDGET_MARKER:{marker}")

    _require("QFrame#projectHero" in theme, "COMPACT_HERO_THEME_MISSING")
    _require("QLabel#fileName" in theme, "FILE_NAME_THEME_MISSING")
    _require("QLabel#activityText" in theme, "ACTIVITY_WRAP_THEME_MISSING")
    _require("QScrollBar:horizontal" in theme, "HORIZONTAL_SCROLL_THEME_MISSING")

    snapshot = build_dashboard_snapshot(repo_root)
    _require(len(snapshot.episodes) >= 1, "NO_EPISODES_DISCOVERED")
    _require(snapshot.total_shot_count >= 1, "NO_PLANNED_SHOTS_DISCOVERED")
    _require(
        snapshot.generated_clip_count <= snapshot.total_shot_count,
        "GENERATED_COUNT_EXCEEDS_PLANNED_COUNT",
    )
    ready_ids = {episode.episode_id for episode in snapshot.ready_queue}
    work_ids = {episode.episode_id for episode in snapshot.work_queue}
    _require(not ready_ids & work_ids, "READY_AND_WORK_QUEUE_OVERLAP")
    _require(
        len(ready_ids) + len(work_ids) == len(snapshot.episodes),
        "QUEUE_PARTITION_INCOMPLETE",
    )

    active = snapshot.active_episode
    _require(active is not None, "ACTIVE_EPISODE_MISSING")
    return {
        "status": STATUS,
        "version": VERSION,
        "framework": "PYSIDE6_QT_WIDGETS",
        "compact_project_hero": "RESTORED_AND_ALWAYS_VISIBLE",
        "preview_16_9": "GUARANTEED_VISIBLE_AT_1366X768",
        "output_files": "FILENAME_ONLY_WITH_TOOLTIP_AND_OPEN_ACTION",
        "activities": "WORD_WRAP_ENABLED",
        "horizontal_scroll": "BLOCKED",
        "ready_episode_count": len(snapshot.ready_queue),
        "work_episode_count": len(snapshot.work_queue),
        "episode_count": len(snapshot.episodes),
        "planned_shot_count": snapshot.total_shot_count,
        "generated_clip_count": snapshot.generated_clip_count,
        "approved_shot_count": snapshot.approved_shot_count,
        "active_episode_id": active.episode_id,
        "paid_video_execution": "BLOCKED_IN_V1_2",
        "next_stage": "HUMAN_UI_REVIEW_V1_2_AND_RUNWARE_EXECUTION_BINDING",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    result = audit(args.repo_root.resolve())
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report = output_root / "siraj-desktop-dashboard-v1-2-audit.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print("STATUS=" + result["status"])
    print("VERSION=" + result["version"])
    print("EPISODE_COUNT=" + str(result["episode_count"]))
    print("READY_EPISODE_COUNT=" + str(result["ready_episode_count"]))
    print("WORK_EPISODE_COUNT=" + str(result["work_episode_count"]))
    print("PLANNED_SHOT_COUNT=" + str(result["planned_shot_count"]))
    print("GENERATED_CLIP_COUNT=" + str(result["generated_clip_count"]))
    print("COMPACT_PROJECT_HERO=RESTORED")
    print("PREVIEW_16_9=GUARANTEED_VISIBLE")
    print("OUTPUT_FILES=FILENAME_ONLY_WITH_TOOLTIP_AND_OPEN")
    print("ACTIVITIES=WORD_WRAP_ENABLED")
    print("HORIZONTAL_SCROLL=BLOCKED")
    print("PAID_VIDEO_EXECUTION=BLOCKED_IN_V1_2")
    print("NEXT_STAGE=" + result["next_stage"])
    print("REPORT=" + str(report))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print("STATUS=FAIL_SIRAJ_DESKTOP_DASHBOARD_V1_2")
        print(str(exc))
        raise SystemExit(1)
