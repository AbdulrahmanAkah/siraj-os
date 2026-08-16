from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.application.desktop_canonical_reference_generation_v1 import (
    accept_reference_asset,
    asset_directory,
    generate_reference_asset,
    issue_desktop_reference_authorization,
    list_statuses,
    load_intake,
    prepare_reference_task,
    reject_reference_asset,
    required_checks,
)


from src.application.visual_context_research_desktop_paid_integration_v1 import (
    execute_prepared_visual_context_research,
    prepare_visual_context_research_from_desktop,
    visual_context_dossier_location,
)

class ReferenceGenerationThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, repo_root: Path, authorization_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.repo_root = Path(repo_root).resolve()
        self.authorization_path = Path(authorization_path)

    def run(self) -> None:
        try:
            result = generate_reference_asset(
                self.repo_root,
                self.authorization_path,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(result)


class VisualContextResearchThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, repo_root: Path, plan) -> None:
        super().__init__()
        self.repo_root = Path(repo_root)
        self.plan = plan

    def run(self) -> None:
        try:
            result = execute_prepared_visual_context_research(
                self.repo_root,
                plan=self.plan,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


class CanonicalReferenceGenerationDock(QDockWidget):
    def __init__(self, window) -> None:
        super().__init__("EP002 Canonical References", window)
        self.window = window
        self.repo_root = Path(window.repo_root).resolve()
        self.worker: ReferenceGenerationThread | None = None
        self.checkboxes: list[QCheckBox] = []

        self.setObjectName("canonicalReferenceGenerationDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )

        body = QWidget(self)
        layout = QVBoxLayout(body)
        title = QLabel("EP002 — Canonical reference generation")
        title.setStyleSheet("font-weight: 800;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Six hash-bound references. Paid generation starts only from this "
            "visible Desktop surface after an explicit click. No automatic retry."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.status_list = QListWidget()
        self.status_list.setMinimumHeight(150)
        layout.addWidget(self.status_list)

        self.preview = QLabel("No candidate selected")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setStyleSheet("border: 1px solid #444;")
        layout.addWidget(self.preview)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(145)
        layout.addWidget(self.details)

        checks_group = QGroupBox("Human acceptance checklist")
        checks_outer = QVBoxLayout(checks_group)
        self.checks_scroll = QScrollArea()
        self.checks_scroll.setWidgetResizable(True)
        self.checks_host = QWidget()
        self.checks_layout = QVBoxLayout(self.checks_host)
        self.checks_scroll.setWidget(self.checks_host)
        checks_outer.addWidget(self.checks_scroll)
        layout.addWidget(checks_group, 1)

        buttons1 = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.generate_btn = QPushButton("Generate selected")
        self.research_btn = QPushButton("Research selected")
        self.open_btn = QPushButton("Open asset folder")
        buttons1.addWidget(self.refresh_btn)
        buttons1.addWidget(self.generate_btn)
        buttons1.addWidget(self.research_btn)
        buttons1.addWidget(self.open_btn)
        layout.addLayout(buttons1)

        buttons2 = QHBoxLayout()
        self.accept_btn = QPushButton("Accept selected")
        self.reject_btn = QPushButton("Reject selected")
        buttons2.addWidget(self.accept_btn)
        buttons2.addWidget(self.reject_btn)
        layout.addLayout(buttons2)

        self.setWidget(body)

        self.refresh_btn.clicked.connect(self.refresh)
        self.generate_btn.clicked.connect(self.generate_selected)
        self.research_btn.clicked.connect(self.research_selected)
        self.accept_btn.clicked.connect(self.accept_selected)
        self.reject_btn.clicked.connect(self.reject_selected)
        self.open_btn.clicked.connect(self.open_assets)
        self.status_list.currentItemChanged.connect(self.render_selected)
        self.refresh()

    def _current_reference_id(self) -> str | None:
        item = self.status_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def refresh(self) -> None:
        current = self._current_reference_id()
        self.status_list.clear()
        target_item = None
        for row in list_statuses(self.repo_root):
            text = (
                f"{row.reference_id} | {row.status} | "
                f"review={row.human_review} | accepted={row.accepted}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, row.reference_id)
            self.status_list.addItem(item)
            if row.reference_id == current:
                target_item = item
        if target_item is not None:
            self.status_list.setCurrentItem(target_item)
        elif self.status_list.count():
            self.status_list.setCurrentRow(0)
        self.render_selected()

    def _clear_checks(self) -> None:
        while self.checks_layout.count():
            child = self.checks_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        self.checkboxes = []

    def render_selected(self, *args) -> None:
        reference_id = self._current_reference_id()
        self._clear_checks()
        if not reference_id:
            self.details.setPlainText("")
            self.preview.setText("No reference selected")
            return
        try:
            prepared = prepare_reference_task(
                repo_root=self.repo_root,
                reference_id=reference_id,
            )
            route = prepared["route"]
            pricing = prepared["pricing"]
            details = (
                f"Reference: {reference_id}\n"
                f"Model: {route['model']}\n"
                f"Route: {route['role']} ({route['reason']})\n"
                f"Dimensions: {route['width']}x{route['height']}\n"
                f"Estimated upper bound: "
                f"{pricing['estimated_upper_bound']:.6f} {pricing['currency']}\n\n"
                f"Prompt:\n{prepared['prompt']}"
            )
        except Exception as exc:
            details = f"Reference: {reference_id}\nPreparation status: {exc}"
        self.details.setPlainText(details)

        try:
            for check in required_checks(self.repo_root, reference_id):
                box = QCheckBox(check)
                self.checkboxes.append(box)
                self.checks_layout.addWidget(box)
            self.checks_layout.addStretch(1)
        except Exception as exc:
            self.details.appendPlainText("\nChecklist error: " + str(exc))

        try:
            intake = load_intake(self.repo_root)
            row = next(
                item
                for item in intake["required_assets"]
                if item["reference_id"] == reference_id
            )
            candidate_text = str(row.get("candidate_path") or "").strip()
            if candidate_text:
                candidate = self.repo_root / candidate_text
                if candidate.is_file():
                    pixmap = QPixmap(str(candidate))
                    if not pixmap.isNull():
                        self.preview.setPixmap(
                            pixmap.scaled(
                                420,
                                240,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        )
                        return
        except Exception:
            pass
        self.preview.setPixmap(QPixmap())
        self.preview.setText("No generated candidate yet")

    def _set_busy(self, busy: bool) -> None:
        self.generate_btn.setEnabled(not busy)
        self.research_btn.setEnabled(not busy)
        self.accept_btn.setEnabled(not busy)
        self.reject_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)

    def generate_selected(self) -> None:
        reference_id = self._current_reference_id()
        if not reference_id:
            QMessageBox.warning(self, "SIRAJ", "Select a reference first.")
            return
        try:
            prepared = prepare_reference_task(
                repo_root=self.repo_root,
                reference_id=reference_id,
            )
        except Exception as exc:
            QMessageBox.warning(self, "SIRAJ", str(exc))
            return
        pricing = prepared["pricing"]
        route = prepared["route"]
        confirmation = QMessageBox.question(
            self,
            "SIRAJ — paid canonical reference generation",
            (
                f"Reference: {reference_id}\n"
                f"Model: {route['model']}\n"
                f"Estimated upper bound: "
                f"{pricing['estimated_upper_bound']:.6f} {pricing['currency']}\n\n"
                "This click starts exactly one initial paid image-generation request.\n"
                "No automatic retry or resubmission is permitted.\n\n"
                "Continue?"
            ),
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            auth = issue_desktop_reference_authorization(
                self.repo_root,
                reference_id,
                prepared,
                desktop_window=self.window,
            )
        except Exception as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            return
        self._set_busy(True)
        self.worker = ReferenceGenerationThread(
            self.repo_root,
            Path(auth["authorization_path"]),
            self,
        )
        self.worker.completed.connect(self._generation_completed)
        self.worker.failed.connect(self._generation_failed)
        self.worker.finished.connect(lambda: self._set_busy(False))
        self.worker.start()

    def _generation_completed(self, result: object) -> None:
        self.refresh()
        QMessageBox.information(
            self,
            "SIRAJ",
            "Candidate generated and preserved pending human review.\n"
            + str(result),
        )

    def _generation_failed(self, error: str) -> None:
        self.refresh()
        QMessageBox.critical(
            self,
            "SIRAJ",
            error + "\n\nNo automatic retry or resubmission was started.",
        )

    def research_selected(self) -> None:
        item = self.status_list.currentItem()
        if item is None:
            QMessageBox.warning(
                self,
                "SIRAJ",
                "Select a reference first.",
            )
            return

        reference_id = str(item.data(Qt.UserRole) or "").strip()
        if not reference_id:
            reference_id = (
                str(item.text() or "")
                .split("|", 1)[0]
                .strip()
                .split()[0]
            )
        if not reference_id:
            QMessageBox.warning(
                self,
                "SIRAJ",
                "Cannot resolve selected reference.",
            )
            return

        dossier = visual_context_dossier_location(
            self.repo_root,
            reference_id=reference_id,
        )
        refresh_existing = False
        refresh_reason = ""

        if dossier.is_file():
            choice = QMessageBox.question(
                self,
                "SIRAJ — visual context research",
                (
                    f"A dossier already exists for {reference_id}.\n\n"
                    "Yes = reuse it without a paid call.\n"
                    "No = refresh it with one explicitly authorized paid "
                    "research call and archive the previous dossier.\n"
                    "Cancel = abort."
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            refresh_existing = (
                choice == QMessageBox.StandardButton.No
            )
            if refresh_existing:
                refresh_reason = (
                    "Human desktop refresh requested for visual context."
                )
        else:
            choice = QMessageBox.question(
                self,
                "SIRAJ — visual context research",
                (
                    f"Research visual context for {reference_id}?\n\n"
                    "This action may make one paid OpenAI/Luna research call "
                    "with web search. No media is generated. Automatic retry "
                    "and automatic resubmission remain forbidden."
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return

        try:
            plan = prepare_visual_context_research_from_desktop(
                self.repo_root,
                reference_id=reference_id,
                refresh_existing=refresh_existing,
                refresh_reason=refresh_reason,
            )
        except Exception as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            return

        self._set_busy(True)
        self._visual_context_thread = VisualContextResearchThread(
            self.repo_root,
            plan,
        )
        self._visual_context_thread.succeeded.connect(
            self._on_visual_context_research_succeeded
        )
        self._visual_context_thread.failed.connect(
            self._on_visual_context_research_failed
        )
        self._visual_context_thread.finished.connect(
            lambda: self._set_busy(False)
        )
        self._visual_context_thread.start()

    def _on_visual_context_research_succeeded(self, result) -> None:
        self.refresh()
        QMessageBox.information(
            self,
            "SIRAJ",
            (
                "Visual-context research completed.\n\n"
                f"status={getattr(result, 'status', 'UNKNOWN')}\n"
                f"provider_calls={getattr(result, 'provider_calls', '')}\n"
                f"web_search_calls={getattr(result, 'web_search_calls', '')}\n"
                f"dossier={getattr(result, 'dossier_path', '')}"
            ),
        )

    def _on_visual_context_research_failed(
        self,
        message: str,
    ) -> None:
        QMessageBox.critical(self, "SIRAJ", str(message))

    def accept_selected(self) -> None:
        reference_id = self._current_reference_id()
        if not reference_id:
            QMessageBox.warning(self, "SIRAJ", "Select a reference first.")
            return
        unchecked = [box.text() for box in self.checkboxes if not box.isChecked()]
        if unchecked:
            QMessageBox.warning(
                self,
                "SIRAJ",
                "All human acceptance checks must be confirmed before PASS.",
            )
            return
        confirmation = QMessageBox.question(
            self,
            "SIRAJ — accept canonical reference",
            (
                f"Accept {reference_id} as the SHA256-bound canonical reference?\n\n"
                "This does not reclassify or regenerate any of the 27 blocked videos."
            ),
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            accept_reference_asset(
                self.repo_root,
                reference_id,
                confirmed_checks=[box.text() for box in self.checkboxes],
            )
        except Exception as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            return
        self.refresh()

    def reject_selected(self) -> None:
        reference_id = self._current_reference_id()
        if not reference_id:
            QMessageBox.warning(self, "SIRAJ", "Select a reference first.")
            return
        reason, ok = QInputDialog.getText(
            self,
            "SIRAJ — reject candidate",
            "Reason:",
        )
        if not ok:
            return
        try:
            reject_reference_asset(
                self.repo_root,
                reference_id,
                reason=reason,
            )
        except Exception as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            return
        self.refresh()

    def open_assets(self) -> None:
        directory = asset_directory(self.repo_root)
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))


def install_canonical_reference_generation_dock(window) -> CanonicalReferenceGenerationDock:
    dock = CanonicalReferenceGenerationDock(window)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    return dock
