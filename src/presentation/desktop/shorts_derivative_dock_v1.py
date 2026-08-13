"""Existing-Desktop dock for the offline Shorts Derivatives workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.application.shorts_derivative_desktop_integration_v1 import ShortsDerivativeDesktopWorkflow
from src.application.shorts_derivative_engine_v1 import ShortsBlockedError

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDockWidget,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional desktop dependency
    Qt = None  # type: ignore[assignment]
    QDockWidget = QFileDialog = QHBoxLayout = QLabel = QListWidget = object  # type: ignore[assignment]
    QListWidgetItem = QMessageBox = QPushButton = QVBoxLayout = QWidget = object  # type: ignore[assignment]
    _QT_AVAILABLE = False


def desktop_dock_descriptor() -> dict[str, Any]:
    return {
        "workflow_id": "SHORTS_DERIVATIVES",
        "label": "Shorts Derivatives",
        "existing_gui": True,
        "second_gui_created": False,
        "actions": [
            "Select Episode",
            "Analyze Episode",
            "View Candidates",
            "Select / Deselect Candidates",
            "View Recommended Portfolio",
            "Generate Local Render Plans",
            "Approve Local Test/Derivative Render Explicitly",
            "View QA Results",
            "Export Approved Package",
        ],
        "hard_boundaries": {
            "provider_calls": False,
            "network_calls": False,
            "paid_calls": False,
            "automatic_publication": False,
            "public_title_owner": "HUMAN",
            "thumbnail_owner": "HUMAN",
        },
    }


if _QT_AVAILABLE:

    class ShortsDerivativeDock(QDockWidget):
        def __init__(self, repo_root: Path, parent: QWidget | None = None) -> None:
            super().__init__("Shorts Derivatives", parent)
            self.repo_root = Path(repo_root).resolve()
            self.workflow = ShortsDerivativeDesktopWorkflow(self.repo_root)
            self.setObjectName("shortsDerivativeDockV1")
            self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

            panel = QWidget(self)
            layout = QVBoxLayout(panel)
            title = QLabel("Shorts Derivatives")
            title.setStyleSheet("font-size: 17px; font-weight: 700; color: #d5b36a;")
            layout.addWidget(title)
            note = QLabel(
                "اشتقاق محلي من الحلقة القائمة فقط. لا Provider، لا Paid، لا Network، ولا نشر تلقائي."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #b7b7b7;")
            layout.addWidget(note)

            select_row = QHBoxLayout()
            select_button = QPushButton("Select Episode")
            select_button.clicked.connect(self._select_episode)
            select_row.addWidget(select_button)
            analyze_button = QPushButton("Analyze Episode")
            analyze_button.clicked.connect(self._analyze_episode)
            select_row.addWidget(analyze_button)
            layout.addLayout(select_row)

            portfolio_row = QHBoxLayout()
            choose_button = QPushButton("Confirm Portfolio")
            choose_button.clicked.connect(self._confirm_portfolio)
            portfolio_row.addWidget(choose_button)
            plans_button = QPushButton("Generate Plans")
            plans_button.clicked.connect(self._generate_plans)
            portfolio_row.addWidget(plans_button)
            layout.addLayout(portfolio_row)

            self.candidates = QListWidget()
            self.candidates.setObjectName("shortsDerivativeCandidatesList")
            layout.addWidget(self.candidates, 1)
            self.status_label = QLabel("BLOCKED — Select an episode")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)
            boundary = QLabel("Provider 0 · Network 0 · Paid 0 · Auto-publish OFF · Title/Thumbnail HUMAN")
            boundary.setWordWrap(True)
            boundary.setStyleSheet("color: #8fbd9a; font-size: 11px;")
            layout.addWidget(boundary)
            self.setWidget(panel)

        def _show_error(self, error: Exception) -> None:
            self.status_label.setText(f"BLOCKED — {error}")
            QMessageBox.warning(self, "Shorts Derivatives", str(error))

        def _select_episode(self) -> None:
            directory = QFileDialog.getExistingDirectory(self, "Select SIRAJ Episode")
            if not directory:
                return
            try:
                self.workflow.select_episode(mode="SIRAJ_NATIVE_EPISODE", episode_directory=Path(directory))
                self.status_label.setText(f"INGESTED — {Path(directory).name}")
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)

        def _analyze_episode(self) -> None:
            try:
                analysis = self.workflow.analyze_episode()
                self.candidates.clear()
                for candidate in analysis.candidates:
                    item = QListWidgetItem(
                        f"{candidate.candidate_id} · {candidate.status} · score={candidate.total_score:.3f} · {candidate.candidate_type}"
                    )
                    item.setData(Qt.ItemDataRole.UserRole, candidate.candidate_id)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    self.candidates.addItem(item)
                self.status_label.setText(f"ANALYZED — {len(analysis.candidates)} candidates; human selection required")
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)

        def _checked_candidate_ids(self) -> list[str]:
            result: list[str] = []
            for index in range(self.candidates.count()):
                item = self.candidates.item(index)
                if item.checkState() == Qt.CheckState.Checked:
                    value = item.data(Qt.ItemDataRole.UserRole)
                    if isinstance(value, str):
                        result.append(value)
            return result

        def _confirm_portfolio(self) -> None:
            try:
                portfolio = self.workflow.select_candidates(self._checked_candidate_ids(), reviewed=True)
                self.status_label.setText(
                    f"PORTFOLIO_READY — {len(portfolio.selected_candidate_ids)} selected · schedule={portfolio.schedule_status}"
                )
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)

        def _generate_plans(self) -> None:
            try:
                plans = self.workflow.generate_render_plans()
                self.status_label.setText(f"RENDER_PLAN_READY — {len(plans)} plan(s); explicit local approval remains required")
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)


else:

    class ShortsDerivativeDock:  # pragma: no cover - optional desktop dependency
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("PySide6 is required for the Shorts Derivatives Desktop dock")


def install_shorts_derivative_dock(window: Any) -> None:
    """Install one dock in the existing Desktop window, if Qt is available."""

    if not _QT_AVAILABLE or getattr(window, "_shorts_derivative_dock_installed", False):
        return
    repo_root = Path(getattr(window, "repo_root", Path.cwd())).resolve()
    dock = ShortsDerivativeDock(repo_root, window)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    window._shorts_derivative_dock_installed = True
    window._shorts_derivative_dock = dock


__all__ = ["ShortsDerivativeDock", "desktop_dock_descriptor", "install_shorts_derivative_dock"]
