from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtWidgets import QApplication

from src.presentation.desktop.production_console import (
    ProductionConsoleDialog,
)


class _RunningWorker:
    def __init__(self, running: bool = True) -> None:
        self.running = running

    def isRunning(self) -> bool:
        return self.running


def test_manual_refresh_is_nonblocking_during_active_production() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = ProductionConsoleDialog(Path.cwd())
    dialog.consolidated_production_worker = _RunningWorker(True)

    started = time.perf_counter()
    dialog._refresh_state()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.25
    assert not dialog.refresh_button.isEnabled()
    assert not dialog.resume_refresh_button.isEnabled()
    assert not dialog.consolidated_v2_refresh.isEnabled()
    assert (
        "أُجّل الفحص الشامل"
        in dialog.consolidated_v2_progress_label.text()
        or "أُجّل الفحص الشامل"
        in dialog.end_to_end_progress_label.text()
    )

    dialog.close()
    app.processEvents()


def test_refresh_controls_reenable_after_worker_finishes() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = ProductionConsoleDialog(Path.cwd())
    worker = _RunningWorker(True)
    dialog.consolidated_production_worker = worker
    dialog._refresh_state()
    assert not dialog.refresh_button.isEnabled()

    worker.running = False
    dialog._siraj_refresh_guard_timer_v1.timeout.emit()
    app.processEvents()

    assert dialog.refresh_button.isEnabled()
    assert dialog.resume_refresh_button.isEnabled()
    assert dialog.consolidated_v2_refresh.isEnabled()

    dialog.close()
    app.processEvents()


def test_source_keeps_refresh_guard_after_all_ui_wrappers() -> None:
    source = Path(
        "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    assert "SIRAJ_ACTIVE_PRODUCTION_REFRESH_GUARD_V1" in source
    assert source.rfind(
        "SIRAJ_ACTIVE_PRODUCTION_REFRESH_GUARD_V1"
    ) > source.rfind(
        "SIRAJ_PRODUCTION_CONSOLE_SINGLE_ACTION_SCROLL_V1"
    )
