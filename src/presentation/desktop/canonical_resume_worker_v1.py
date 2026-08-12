"""Qt worker used by the full SIRAJ desktop UI.

The worker is deliberately a thin presentation boundary.  All state checks,
compare-and-set protection, durable result handling, and stage execution stay
in :class:`DesktopProductionResumeController`; this class never talks to a
provider and never chooses a stage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QObject, QThread, Signal

from src.application.desktop_resume_readiness_v1 import (
    DesktopProductionResumeController,
    DesktopResumeIntent,
)


class CanonicalDesktopResumeWorker(QThread):
    """Run one already-reviewed canonical desktop transaction."""

    entered = Signal()
    heartbeat = Signal()
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        controller: DesktopProductionResumeController,
        intent: DesktopResumeIntent,
        authorization: Mapping[str, Any],
        *,
        result_path: Path | None = None,
        provider_gateway: Any | None = None,
        fault_injector: Any | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.intent = intent
        self.authorization = authorization
        self.result_path = result_path
        self.provider_gateway = provider_gateway
        self.fault_injector = fault_injector

    def run(self) -> None:
        self.entered.emit()
        self.heartbeat.emit()
        try:
            result = self.controller.execute_confirmed_resume(
                self.intent,
                authorization=self.authorization,
                result_path=self.result_path,
                provider_gateway=self.provider_gateway,
                fault_injector=self.fault_injector,
                progress_callback=self.progress.emit
                if self.intent.first_stage == "PROVIDER_EXECUTION"
                else None,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.heartbeat.emit()
        self.completed.emit(result)
