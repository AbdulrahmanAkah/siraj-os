from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.presentation.desktop.production_console import (
        ProductionConsoleDialog,
    )

    app = QApplication.instance() or QApplication(
        ["siraj-episode-production-control-v1"]
    )
    with tempfile.TemporaryDirectory() as temporary:
        smoke_repo = Path(temporary)
        required = (
            "projects/episode-001-adam/cinematic/shot-packages/"
            "adam-dc2-s02-sh03/veo-shot-pack-001-v1.json",
            "projects/episode-001-adam/contracts/"
            "runware-beat-01-execution-authorization-v1.json",
            "projects/episode-001-adam/contracts/"
            "automatic-video-user-authorization-v1.json",
            "projects/episode-001-adam/contracts/"
            "episode-production-policy-v1.json",
            "projects/episode-001-adam/cinematic/"
            "episode-production-plan-v1.json",
        )
        for relative in required:
            source = repo / relative
            destination = smoke_repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        dialog = ProductionConsoleDialog(smoke_repo)
        dialog.show()
        for _ in range(8):
            app.processEvents()

        require(dialog.isVisible(), "DIALOG_NOT_VISIBLE")
        tabs = dialog.findChild(QTabWidget, "episodeProductionTabs")
        table = dialog.findChild(
            QTableWidget,
            "episodeProductionQueueTable",
        )
        generate = dialog.findChild(QPushButton, "generateVideoButton")
        view = dialog.findChild(QPushButton, "viewVideoButton")
        location = dialog.findChild(
            QPushButton,
            "showVideoLocationButton",
        )
        score = dialog.findChild(QSpinBox, "finalScoreSpinBox")

        require(tabs is not None and tabs.count() == 2, "TABS_MISSING")
        require(table is not None and table.rowCount() == 70, "QUEUE_NOT_70")
        require(generate is not None, "GENERATE_BUTTON_MISSING")
        require(view is not None, "VIEW_BUTTON_MISSING")
        require(location is not None, "LOCATION_BUTTON_MISSING")
        require(score is not None, "SCORE_INPUT_MISSING")
        require(score.minimum() == 0 and score.maximum() == 100, "SCORE_RANGE")

        args.output_root.mkdir(parents=True, exist_ok=True)
        screenshot = (
            args.output_root
            / "siraj-episode-production-control-v1.png"
        )
        dialog.grab().save(str(screenshot))
        print("STATUS=PASS_SIRAJ_EPISODE_PRODUCTION_CONTROL_V1_SMOKE")
        print("QUEUE_ROWS=70")
        print("PLAN_TABS=2")
        print("PAID_EXECUTION_DURING_SMOKE=NO")
        print("RUNWARE_REQUESTS_DURING_SMOKE=0")
        print("SCREENSHOT=" + str(screenshot))
        dialog.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
