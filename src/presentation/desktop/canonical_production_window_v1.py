"""Internal readiness/debug window (not the production UI).

The supported production composition root is ``SirajDesktopWindow`` in
``main_window.py``.  This small window is retained only for diagnostics and
never exposes a provider execution route.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget

from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    DesktopProductionResumeController,
    DesktopResumeIntent,
    DesktopResumePolicyError,
)
from .canonical_resume_worker_v1 import CanonicalDesktopResumeWorker

# Compatibility name for the internal readiness window.  The full designed
# UI uses the same shared worker through its canonical controller binding.
_MediaCostPreflightWorker = CanonicalDesktopResumeWorker


class CanonicalProductionDesktopWindow(QMainWindow):
    def __init__(self, repo_root: Path) -> None:
        super().__init__()
        self.controller = DesktopProductionResumeController(repo_root)
        self._worker: _MediaCostPreflightWorker | None = None
        self.setWindowTitle("SIRAJ Internal Readiness / Debug")
        self.setMinimumSize(720, 420)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QWidget(self)
        layout = QVBoxLayout(root)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.review = QPushButton("Refresh authoritative episode state")
        self.resume = QPushButton("Resume the next authoritative stage locally")
        self.review.clicked.connect(self.refresh_authoritative_state)
        self.resume.clicked.connect(self.request_explicit_resume)
        layout.addWidget(self.summary)
        layout.addWidget(self.review)
        layout.addWidget(self.resume)
        layout.addStretch(1)
        self.setCentralWidget(root)
        self.refresh_authoritative_state()

    def refresh_authoritative_state(self) -> None:
        try:
            state = self.controller.inspect()
        except DesktopResumePolicyError as exc:
            self.summary.setText("Authoritative state unavailable: " + str(exc))
            self.resume.setEnabled(False)
            return
        self.resume.setEnabled(state.current_stage == "MEDIA_COST_PREFLIGHT")
        self.summary.setText(
            "Episode: " + state.episode_id
            + "\nCurrent stage: " + state.current_stage
            + "\nPrevious alignment gate: " + state.alignment_gate
            + "\nDuplicate/similarity gate: " + state.duplicate_gate
            + "\nProduction status: PAUSED / AWAITING HUMAN RESUME"
            + "\nResume entrypoint: DESKTOP_UI_ONLY"
        )

    def request_explicit_resume(self) -> None:
        """Confirm and execute only the current local stage from the Desktop UI."""

        try:
            intent = self.controller.prepare_resume(source=DESKTOP_SOURCE)
        except DesktopResumePolicyError as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            return
        confirmation = QMessageBox.question(
            self,
            "SIRAJ",
            "This explicit Desktop action will run the local canonical stage: "
            + intent.first_stage
            + ".\nNo provider call or downstream stage will be made. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        authorization = {
            "authorization_id": "desktop-ui-local-" + uuid.uuid4().hex,
            "source": DESKTOP_SOURCE,
            "scope": "MEDIA_COST_PREFLIGHT_LOCAL_ONLY",
            "episode_id": intent.episode_id,
            "provider_calls": 0,
            "paid_operation": False,
        }
        self.resume.setEnabled(False)
        worker = _MediaCostPreflightWorker(
            self.controller,
            intent,
            authorization,
            parent=self,
        )
        self._worker = worker
        worker.completed.connect(self._preflight_completed)
        worker.failed.connect(self._preflight_failed)
        worker.finished.connect(self._preflight_finished)
        worker.start()

    def _preflight_completed(self, result: object) -> None:
        QMessageBox.information(
            self,
            "SIRAJ",
            "MEDIA_COST_PREFLIGHT completed locally. Next stage is exposed but was not started.",
        )

    def _preflight_failed(self, error: str) -> None:
        QMessageBox.critical(self, "SIRAJ", "MEDIA_COST_PREFLIGHT stopped: " + error)

    def _preflight_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self.refresh_authoritative_state()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            self.hide()
            return
        event.accept()
