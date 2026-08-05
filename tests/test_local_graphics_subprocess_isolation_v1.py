from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from src.application.desktop_media_execution_v1 import (
    LOCAL_GRAPHICS_CHILD_MODULE,
    _local_graphics_subprocess_command,
    _local_graphics_subprocess_environment,
)


def test_local_graphics_worker_uses_current_interpreter(tmp_path):
    command = _local_graphics_subprocess_command(tmp_path, "LOCAL-SH-005")
    assert command[0] == sys.executable
    assert command[1:3] == ["-m", LOCAL_GRAPHICS_CHILD_MODULE]
    assert "--repo-root" in command
    assert "--queue-id" in command
    assert command[-1] == "LOCAL-SH-005"


def test_local_graphics_worker_environment_is_offscreen():
    environment = _local_graphics_subprocess_environment()
    assert environment["QT_QPA_PLATFORM"] == "offscreen"
    assert environment["QT_QUICK_BACKEND"] == "software"
    assert environment["QSG_RHI_BACKEND"] == "software"


def test_child_process_can_own_qgui_application():
    repo = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.update(_local_graphics_subprocess_environment())
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            LOCAL_GRAPHICS_CHILD_MODULE,
            "--self-test",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
        timeout=60,
    )
    assert process.returncode == 0, process.stderr
    assert '"status": "PASS"' in process.stdout
    assert '"qt_platform": "offscreen"' in process.stdout
