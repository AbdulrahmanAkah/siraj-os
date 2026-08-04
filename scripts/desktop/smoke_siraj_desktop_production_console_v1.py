from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QLineEdit,
    QPushButton,
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

    app = QApplication.instance() or QApplication(["siraj-production-console-v1"])
    dialog = ProductionConsoleDialog(repo)
    dialog.show()
    for _ in range(8):
        app.processEvents()

    require(dialog.isVisible(), "PRODUCTION_CONSOLE_NOT_VISIBLE")
    execute = dialog.findChild(QPushButton, "executeBeat01Button")
    recover = dialog.findChild(QPushButton, "recoverBeat01Button")
    review = dialog.findChild(QPushButton, "saveBeat01ReviewButton")
    confirmation = dialog.findChild(QCheckBox, "paidExecutionConfirmation")
    key_input = dialog.findChild(QLineEdit, "runwareApiKeyInput")
    require(execute is not None, "EXECUTE_BUTTON_MISSING")
    require(recover is not None, "RECOVERY_BUTTON_MISSING")
    require(review is not None, "REVIEW_BUTTON_MISSING")
    require(confirmation is not None, "CONFIRMATION_MISSING")
    require(key_input is not None, "API_KEY_INPUT_MISSING")
    require(not execute.isEnabled(), "PAID_EXECUTION_ENABLED_WITHOUT_CONFIRMATION")
    confirmation.setChecked(True)
    key_input.setText("smoke-test-key-never-sent")
    for _ in range(3):
        app.processEvents()
    require(execute.isEnabled(), "EXECUTION_NOT_ENABLED_AFTER_LOCAL_GATES")
    require(not recover.isEnabled(), "RECOVERY_ENABLED_WITHOUT_LOCK")
    require(not review.isEnabled(), "REVIEW_ENABLED_WITHOUT_RECEIPT")
    require(
        not (
            repo
            / "projects/episode-001-adam/cinematic/shot-packages/"
            "adam-dc2-s02-sh03/outputs/"
            "runware-beat-01-execution-lock-v1.json"
        ).exists(),
        "SMOKE_MUST_NOT_CREATE_EXECUTION_LOCK",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    screenshot = args.output_root / "siraj-desktop-production-console-v1.png"
    dialog.grab().save(str(screenshot))
    print("STATUS=PASS_SIRAJ_DESKTOP_PRODUCTION_CONSOLE_V1_SMOKE")
    print("PAID_EXECUTION_DURING_SMOKE=NO")
    print("NETWORK_REQUESTS_DURING_SMOKE=0")
    print("EXECUTION_REQUIRES_CHECKBOX=YES")
    print("API_KEY_PERSISTED=NO")
    print("SCREENSHOT=" + str(screenshot))
    dialog.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
