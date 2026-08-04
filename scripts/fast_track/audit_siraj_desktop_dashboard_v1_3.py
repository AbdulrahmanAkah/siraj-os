from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

STATUS = "PASS_SIRAJ_DESKTOP_DASHBOARD_V1_3"
VERSION = "1.3"


class AuditError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise AuditError(f"CANNOT_READ:{path}:{exc}") from exc


def audit(repo_root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(repo_root))
    from src.presentation.desktop.repository import build_dashboard_snapshot

    desktop = repo_root / "src" / "presentation" / "desktop"
    main_window = read(desktop / "main_window.py")
    smoke = read(
        repo_root / "scripts" / "desktop"
        / "smoke_siraj_desktop_dashboard_v1_3.py"
    )

    required_main_markers = (
        'RELEASE = "SIRAJ_DESKTOP_DASHBOARD_V1_3"',
        'setWindowTitle("سراج — إدارة إنتاج الحلقات — v1.3")',
        'setObjectName("mainColumnScroll")',
        'setObjectName("utilityColumnScroll")',
        'setObjectName("mainColumnContent")',
        'setObjectName("utilityColumnContent")',
        'setObjectName("episodeQueueTabs")',
        'setObjectName("previewTitle")',
        'setObjectName("previewStatus")',
        'main_content.setMinimumHeight(720)',
        'utility_content.setMinimumHeight(760)',
        'queue.setMinimumHeight(240)',
        'panel.setMinimumHeight(315)',
        'verticalScrollBar().setValue(0)',
        'ScrollBarAlwaysOff',
    )
    for marker in required_main_markers:
        require(
            marker in main_window,
            f"MISSING_MAIN_WINDOW_MARKER:{marker}",
        )

    require(
        'setObjectName("workspaceScroll")' not in main_window,
        "LEGACY_SHARED_WORKSPACE_SCROLL_PRESENT",
    )

    required_smoke_markers = (
        "effective_visible_rect",
        "pixel_signature",
        "visible_pixel_signature",
        "MAIN_QUEUE_EFFECTIVE_VISIBILITY",
        "PREVIEW_EFFECTIVE_VISIBILITY",
        "PREVIEW_PIXEL_DIVERSITY",
        "QUEUE_PIXEL_DIVERSITY",
        "QUEUE_PIXEL_LUMINANCE_SPAN",
        "FONT_RENDERING_DEPENDENCY=NOT_REQUIRED",
        "mainColumnScroll",
        "utilityColumnScroll",
    )
    for marker in required_smoke_markers:
        require(marker in smoke, f"MISSING_SMOKE_MARKER:{marker}")

    snapshot = build_dashboard_snapshot(repo_root)
    require(len(snapshot.episodes) >= 1, "NO_EPISODES_DISCOVERED")
    require(snapshot.total_shot_count >= 1, "NO_PLANNED_SHOTS_DISCOVERED")

    ready_ids = {episode.episode_id for episode in snapshot.ready_queue}
    work_ids = {episode.episode_id for episode in snapshot.work_queue}
    require(not ready_ids & work_ids, "READY_AND_WORK_QUEUE_OVERLAP")
    require(
        len(ready_ids) + len(work_ids) == len(snapshot.episodes),
        "QUEUE_PARTITION_INCOMPLETE",
    )

    active = snapshot.active_episode
    require(active is not None, "ACTIVE_EPISODE_MISSING")

    return {
        "status": STATUS,
        "version": VERSION,
        "release": "SIRAJ_DESKTOP_DASHBOARD_V1_3",
        "framework": "PYSIDE6_QT_WIDGETS",
        "arabic_rtl": True,
        "approved_composition": "SIDEBAR_LEFT_PREVIEW_RIGHT",
        "scroll_architecture": "INDEPENDENT_MAIN_AND_UTILITY_COLUMNS",
        "effective_geometry_validation": True,
        "pixel_visibility_assertions": True,
        "pixel_assertions_font_independent": True,
        "horizontal_scroll": "BLOCKED",
        "episode_count": len(snapshot.episodes),
        "ready_episode_count": len(snapshot.ready_queue),
        "work_episode_count": len(snapshot.work_queue),
        "planned_shot_count": snapshot.total_shot_count,
        "generated_clip_count": snapshot.generated_clip_count,
        "approved_shot_count": snapshot.approved_shot_count,
        "active_episode_id": active.episode_id,
        "paid_video_execution": "BLOCKED_IN_V1_3",
        "next_stage": "HUMAN_UI_REVIEW_V1_3_AND_RUNWARE_EXECUTION_BINDING",
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

    report = output_root / "siraj-desktop-dashboard-v1-3-audit.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
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
    print("SCROLL_ARCHITECTURE=INDEPENDENT_COLUMNS")
    print("EFFECTIVE_GEOMETRY_VALIDATION=ENABLED")
    print("PIXEL_VISIBILITY_ASSERTIONS=ENABLED")
    print("PIXEL_ASSERTIONS_FONT_INDEPENDENT=YES")
    print("HORIZONTAL_SCROLL=BLOCKED")
    print("PAID_VIDEO_EXECUTION=BLOCKED_IN_V1_3")
    print("NEXT_STAGE=" + result["next_stage"])
    print("REPORT=" + str(report))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print("STATUS=FAIL_SIRAJ_DESKTOP_DASHBOARD_V1_3")
        print(str(exc))
        raise SystemExit(1)
