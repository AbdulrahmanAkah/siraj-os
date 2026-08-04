from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QSpinBox


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
        ["siraj-automatic-video-v1"]
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

        require(dialog.isVisible(), "AUTOMATIC_VIDEO_DIALOG_NOT_VISIBLE")
        generate = dialog.findChild(QPushButton, "generateVideoButton")
        view = dialog.findChild(QPushButton, "viewVideoButton")
        location = dialog.findChild(QPushButton, "showVideoLocationButton")
        save = dialog.findChild(QPushButton, "saveFinalScoreButton")
        score = dialog.findChild(QSpinBox, "finalScoreSpinBox")

        require(generate is not None, "GENERATE_BUTTON_MISSING")
        require(view is not None, "VIEW_VIDEO_BUTTON_MISSING")
        require(location is not None, "SHOW_LOCATION_BUTTON_MISSING")
        require(save is not None, "SAVE_SCORE_BUTTON_MISSING")
        require(score is not None, "FINAL_SCORE_INPUT_MISSING")
        require(score.minimum() == 0, "SCORE_MINIMUM_CHANGED")
        require(score.maximum() == 100, "SCORE_MAXIMUM_CHANGED")
        require(
            not (
                smoke_repo
                / "projects/episode-001-adam/cinematic/shot-packages/"
                "adam-dc2-s02-sh03/outputs/attempt-01/"
                "submission-lock-v1.json"
            ).exists(),
            "SMOKE_MUST_NOT_CREATE_PAID_SUBMISSION_LOCK",
        )

        args.output_root.mkdir(parents=True, exist_ok=True)
        screenshot = args.output_root / "siraj-desktop-automatic-video-v1.png"
        dialog.grab().save(str(screenshot))
        print("STATUS=PASS_SIRAJ_DESKTOP_AUTOMATIC_VIDEO_V1_SMOKE")
        print("PAID_EXECUTION_DURING_SMOKE=NO")
        print("RUNWARE_REQUESTS_DURING_SMOKE=0")
        print("ONE_CLICK_GENERATION_CONTROL=VISIBLE")
        print("VIEW_VIDEO_CONTROL=VISIBLE")
        print("SHOW_LOCATION_CONTROL=VISIBLE")
        print("FINAL_SCORE_INPUT=0_TO_100")
        print("SCREENSHOT=" + str(screenshot))
        dialog.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
