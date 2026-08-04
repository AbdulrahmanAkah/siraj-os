from __future__ import annotations

import argparse
import json
from pathlib import Path
import py_compile
import sys

_REPO_ROOT_FROM_SCRIPT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_FROM_SCRIPT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FROM_SCRIPT))

from src.presentation.desktop.repository import build_dashboard_snapshot


REQUIRED_FILES = (
    "src/presentation/desktop/app.py",
    "src/presentation/desktop/main_window.py",
    "src/presentation/desktop/models.py",
    "src/presentation/desktop/repository.py",
    "src/presentation/desktop/theme.py",
    "src/presentation/desktop/widgets.py",
    "scripts/desktop/launch_siraj_desktop.py",
    "scripts/desktop/run_siraj_desktop.ps1",
    "docs/design/assets/siraj-desktop-dashboard-concept-v1.png",
    "projects/siraj-desktop/evidence/desktop-dashboard-concept-human-approval-v1.json",
    "projects/siraj-desktop/contracts/desktop-dashboard-implementation-binding-v1.json",
)


def audit(repo_root: Path) -> dict[str, object]:
    missing = [relative for relative in REQUIRED_FILES if not (repo_root / relative).is_file()]
    if missing:
        raise ValueError("MISSING_DESKTOP_FILES:" + ",".join(missing))

    for relative in (
        "src/presentation/desktop/app.py",
        "src/presentation/desktop/main_window.py",
        "src/presentation/desktop/models.py",
        "src/presentation/desktop/repository.py",
        "src/presentation/desktop/theme.py",
        "src/presentation/desktop/widgets.py",
    ):
        py_compile.compile(str(repo_root / relative), doraise=True)

    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8-sig")
    if 'siraj-desktop = "src.presentation.desktop.app:main"' not in pyproject:
        raise ValueError("DESKTOP_ENTRY_POINT_MISSING")
    if 'desktop = ["PySide6>=6.10,<7"]' not in pyproject:
        raise ValueError("DESKTOP_OPTIONAL_DEPENDENCY_MISSING")

    snapshot = build_dashboard_snapshot(repo_root)
    return {
        "status": "PASS_SIRAJ_DESKTOP_DASHBOARD_V1",
        "episode_count": len(snapshot.episodes),
        "ready_for_conversion_count": len(snapshot.ready_for_conversion),
        "publish_ready_count": len(snapshot.publish_ready),
        "total_shot_count": snapshot.total_shot_count,
        "active_episode_id": snapshot.active_episode_id,
        "video_execution": "NOT_IMPLEMENTED_IN_V1",
        "next_stage": "LOCAL_PYSIDE6_INSTALL_AND_HUMAN_UI_REVIEW",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    report = audit(args.repo_root.resolve())
    args.output_root.mkdir(parents=True, exist_ok=True)
    report_path = args.output_root / "siraj-desktop-dashboard-v1-audit.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for key, value in report.items():
        print(f"{key.upper()}={value}")
    print(f"REPORT={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
