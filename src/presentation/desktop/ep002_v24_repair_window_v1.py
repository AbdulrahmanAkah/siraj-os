"""Desktop-only launch surface for the approved EP002 V2.4 repair generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from src.application.ep002_v24_repair_provider_execution_v1 import (
    DESKTOP_SOURCE,
    EP002V24DesktopRepairExecutionService,
    EP002V24RepairExecutionError,
    V24ExecutionPreview,
)


class V24RepairWorker(QThread):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: EP002V24DesktopRepairExecutionService,
        capability: object,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.capability = capability

    def run(self) -> None:
        try:
            outcome = self.service.execute(
                self.capability,
                source=DESKTOP_SOURCE,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(outcome)


class EP002V24RepairProductionDialog(QDialog):
    """Explicit human Desktop boundary; no paid call occurs before Start."""

    def __init__(self, repo_root: Path, parent: Any = None) -> None:
        super().__init__(parent)
        self.repo_root = Path(repo_root).resolve()
        self.service = EP002V24DesktopRepairExecutionService(self.repo_root)
        self.worker: V24RepairWorker | None = None

        self.setWindowTitle("SIRAJ — EP002 V2.4 Approved Visual Repair")
        self.resize(780, 620)
        self.setMinimumSize(700, 540)

        layout = QVBoxLayout(self)
        title = QLabel("EP002 — V2.4 Final Approved Visual Repair")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        warning = QLabel(
            "هذا المسار ينتج المرئيات الجديدة فقط. لا مونتاج، لا QA، "
            "ولا إعادة محاولة مدفوعة تلقائيًا. يتوقف فورًا عند أول فشل/نتيجة غير محسومة."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("font-size: 14px;")
        layout.addWidget(warning)

        self.summary = QLabel()
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log, 1)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("تحديث التحقق")
        self.refresh_button.clicked.connect(self.refresh_preview)
        buttons.addWidget(self.refresh_button)

        buttons.addStretch(1)

        self.start_button = QPushButton("ابدأ إنتاج V2.4 المعتمد")
        self.start_button.setMinimumHeight(42)
        self.start_button.clicked.connect(self.start_production)
        buttons.addWidget(self.start_button)

        self.close_button = QPushButton("إغلاق")
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)

        layout.addLayout(buttons)
        self.refresh_preview()

    def _render_preview(self, preview: V24ExecutionPreview) -> None:
        self.summary.setText(
            "Storyboard SHA256:\n"
            f"{preview.storyboard_sha256}\n\n"
            f"الوحدات: {preview.planned_units} | مكتمل: {preview.completed_units} | "
            f"متبقٍ: {preview.remaining_units}\n"
            f"ثواني المزود: {preview.provider_seconds}\n"
            f"التكلفة المخططة: ${preview.expected_cost_usd:.2f} | "
            f"السقف الصلب: ${preview.maximum_cost_usd:.2f}\n"
            f"الحالة: {preview.status}"
        )
        self.start_button.setEnabled(preview.execution_allowed)
        if preview.review_package_path:
            self.log.appendPlainText(
                "REVIEW_PACKAGE=" + preview.review_package_path
            )
        if preview.unresolved_unit_ids:
            self.log.appendPlainText(
                "BLOCKED_UNRESOLVED="
                + ",".join(preview.unresolved_unit_ids)
            )

    def refresh_preview(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            preview = self.service.inspect()
        except Exception as exc:
            self.summary.setText("BLOCKED: " + str(exc))
            self.start_button.setEnabled(False)
            self.log.appendPlainText("PRECHECK_FAILED " + str(exc))
            return
        self._render_preview(preview)
        self.log.appendPlainText("PRECHECK_PASS " + preview.status)

    def start_production(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            preview = self.service.inspect()
        except Exception as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            return
        if not preview.execution_allowed:
            QMessageBox.warning(
                self,
                "SIRAJ",
                "الإنتاج غير مسموح في الحالة الحالية:\n" + preview.status,
            )
            return

        message = (
            "سيبدأ الآن إنتاج Storyboard V2.4 المعتمد فقط.\n\n"
            f"• {preview.remaining_units} محاولات أولى متبقية من أصل {preview.planned_units}\n"
            f"• إجمالي الخطة: {preview.provider_seconds} ثانية Veo 3.1 Lite 720p\n"
            f"• التكلفة المخططة الكاملة: ${preview.expected_cost_usd:.2f}\n"
            f"• السقف الصلب: ${preview.maximum_cost_usd:.2f}\n\n"
            "لا توجد إعادة محاولة أو إعادة إرسال تلقائية. "
            "عند أول FAILED/UNKNOWN يتوقف التنفيذ ولا ينتقل للوحدة التالية.\n"
            "بعد اكتمال المرئيات يتوقف المسار للمراجعة البشرية قبل المونتاج.\n\n"
            "هل تريد بدء المحاولات الأولى المدفوعة الآن؟"
        )
        answer = QMessageBox.question(
            self,
            "SIRAJ — V2.4 paid first attempts",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.log.appendPlainText("USER_CANCELLED_NO_PAID_CALL")
            return

        try:
            capability = self.service.issue_desktop_capability(
                source=DESKTOP_SOURCE
            )
        except EP002V24RepairExecutionError as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            return

        self.start_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.log.appendPlainText("DESKTOP_EXPLICIT_START_CONFIRMED")

        worker = V24RepairWorker(self.service, capability, self)
        self.worker = worker
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        worker.start()

    def _on_progress(self, payload: object) -> None:
        if not isinstance(payload, Mapping):
            return
        status = str(payload.get("status") or "")
        unit_id = str(payload.get("unit_id") or "")
        completed = payload.get("completed_units", "")
        planned = payload.get("planned_units", "")
        exposure = payload.get("planned_exposure_usd")
        suffix = (
            f" exposure=${float(exposure):.2f}"
            if isinstance(exposure, (int, float))
            else ""
        )
        self.log.appendPlainText(
            f"{status} {unit_id} {completed}/{planned}{suffix}"
        )

    def _on_completed(self, outcome: object) -> None:
        status = getattr(outcome, "status", "COMPLETE")
        review = getattr(outcome, "review_package_path", None)
        completed = getattr(outcome, "completed_units", None)
        self.log.appendPlainText(
            f"PROVIDER_STAGE_COMPLETE completed={completed} status={status}"
        )
        QMessageBox.information(
            self,
            "SIRAJ",
            "اكتملت المحاولات الأولى المخططة لـV2.4.\n"
            "لم يبدأ المونتاج أو QA.\n\n"
            f"حزمة المراجعة البصرية:\n{review}\n\n"
            "الخطوة التالية: مراجعة المرئيات الفعلية قبل المونتاج.",
        )

    def _on_failed(self, error: str) -> None:
        self.log.appendPlainText("STOPPED_NO_RETRY " + error)
        QMessageBox.critical(
            self,
            "SIRAJ — stopped safely",
            "توقف إنتاج V2.4.\n\n"
            + error
            + "\n\nلم تُنفذ أي إعادة محاولة/إرسال تلقائي، "
            "ولم يبدأ المونتاج.",
        )

    def _on_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.refresh_preview()

    def closeEvent(self, event: Any) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(
                self,
                "SIRAJ",
                "لا يمكن إغلاق نافذة V2.4 أثناء وجود عملية مزود نشطة.",
            )
            event.ignore()
            return
        super().closeEvent(event)


def run_v24_repair_desktop(repo_root: Path) -> int:
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication([])
    dialog = EP002V24RepairProductionDialog(repo_root)
    dialog.show()
    if owns_app:
        return int(app.exec())
    return 0


__all__ = [
    "EP002V24RepairProductionDialog",
    "V24RepairWorker",
    "run_v24_repair_desktop",
]
