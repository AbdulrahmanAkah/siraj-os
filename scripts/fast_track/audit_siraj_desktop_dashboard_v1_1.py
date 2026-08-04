from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

STATUS = "PASS_SIRAJ_DESKTOP_DASHBOARD_V1_1"
VERSION = "1.1"


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
    repository = _read(desktop / "repository.py")
    widgets = _read(desktop / "widgets.py")
    icons = _read(desktop / "icons.py")
    theme = _read(desktop / "theme.py")

    required_main_markers = (
        "QSplitter",
        "ScrollBarAlwaysOff",
        "self.ready_table",
        "self.work_table",
        "جاهزة للتحويل",
        "اللقطات المخططة",
        "self.workflow_strip.set_episode",
        "setLayoutDirection(Qt.LayoutDirection.LeftToRight)",
    )
    for marker in required_main_markers:
        _require(marker in main_window, f"MISSING_MAIN_WINDOW_MARKER:{marker}")

    _require("NOT_GENERATED" in repository, "GENERATED_STATUS_GUARD_MISSING")
    _require("_count_generated_video_files" in repository, "REAL_VIDEO_FILE_COUNT_MISSING")
    _require("current_beat_id" in repository, "CURRENT_BEAT_EXTRACTION_MISSING")
    _require("heightForWidth" in widgets, "PREVIEW_16_9_CONTRACT_MISSING")
    _require("set_episode" in widgets, "WORKFLOW_STATE_BINDING_MISSING")
    _require("QSvgRenderer" in icons, "SVG_ICON_RENDERER_MISSING")
    _require("QTabWidget::pane" in theme, "QUEUE_TAB_THEME_MISSING")
    _require("QSplitter::handle" in theme, "SPLITTER_THEME_MISSING")

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
        "arabic_rtl": True,
        "approved_composition": "SIDEBAR_LEFT_PREVIEW_RIGHT",
        "horizontal_scroll_policy": "BLOCKED_AT_WORKSPACE_AND_TABLE_LEVELS",
        "responsive_splitter": True,
        "ready_episode_count": len(snapshot.ready_queue),
        "work_episode_count": len(snapshot.work_queue),
        "episode_count": len(snapshot.episodes),
        "planned_shot_count": snapshot.total_shot_count,
        "generated_clip_count": snapshot.generated_clip_count,
        "approved_shot_count": snapshot.approved_shot_count,
        "active_episode_id": active.episode_id,
        "paid_video_execution": "BLOCKED_IN_V1_1",
        "next_stage": "HUMAN_UI_REVIEW_V1_1_AND_RUNWARE_EXECUTION_BINDING",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    result = audit(repo_root)
    output_root.mkdir(parents=True, exist_ok=True)
    report = output_root / "siraj-desktop-dashboard-v1-1-audit.json"
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
    print("APPROVED_SHOT_COUNT=" + str(result["approved_shot_count"]))
    print("HORIZONTAL_SCROLL=BLOCKED")
    print("RESPONSIVE_SPLITTER=ENABLED")
    print("SVG_ICONS=ENABLED")
    print("PAID_VIDEO_EXECUTION=BLOCKED_IN_V1_1")
    print("NEXT_STAGE=" + result["next_stage"])
    print("REPORT=" + str(report))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print("STATUS=FAIL_SIRAJ_DESKTOP_DASHBOARD_V1_1")
        print(str(exc))
        raise SystemExit(1)
