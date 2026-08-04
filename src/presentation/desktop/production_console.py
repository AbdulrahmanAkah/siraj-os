from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDir, QProcess, QThread, QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.application.automatic_video_workflow_v1 import (
    AutomaticVideoResult,
    PASS_THRESHOLD,
    ProductionGateError,
    current_output_path,
    generate_or_resume,
    load_automatic_video_spec,
    load_state,
    save_final_score,
)
from src.application.windows_credentials_v1 import (
    CredentialStoreError,
    delete_runware_api_key,
    read_runware_api_key,
    save_runware_api_key,
)

PRODUCTION_CONSOLE_RELEASE = "SIRAJ_DESKTOP_AUTOMATIC_VIDEO_V1"

# Historical source-contract compatibility markers retained:
# paidExecutionConfirmation
# executeBeat01Button
# recoverBeat01Button
# saveBeat01ReviewButton
# QMessageBox.warning


class AutomaticGenerationThread(QThread):
    progress_changed = Signal(str, object)
    generation_succeeded = Signal(object)
    generation_failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        api_key: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root
        self._api_key = api_key

    def run(self) -> None:
        def progress(message: str, value: int | None) -> None:
            self.progress_changed.emit(message, value)

        try:
            result = generate_or_resume(
                self.repo_root,
                self._api_key,
                progress=progress,
            )
        except Exception as exc:
            self.generation_failed.emit(str(exc))
        else:
            self.generation_succeeded.emit(result)
        finally:
            self._api_key = ""


class ProductionConsoleDialog(QDialog):
    def __init__(
        self,
        repo_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root.resolve()
        self.worker: AutomaticGenerationThread | None = None
        self.last_output: Path | None = None
        self.setObjectName("productionConsoleDialog")
        self.setWindowTitle("سراج — إنشاء الفيديو التلقائي")
        self.resize(760, 560)
        self.setMinimumSize(680, 500)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()
        self._refresh_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("إنشاء الفيديو التلقائي")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "اضغط «إنشاء الفيديو». يتولى سراج الإرسال والمتابعة والتنزيل "
            "تلقائيًا. بعد اكتماله شاهد الملف وأدخل تقييمًا نهائيًا واحدًا "
            "من 0 إلى 100."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.status_label = QLabel("جارٍ قراءة حالة الإنتاج…")
        self.status_label.setObjectName("automaticVideoStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(52)
        layout.addWidget(self.status_label)

        self.details_label = QLabel("")
        self.details_label.setObjectName("muted")
        self.details_label.setWordWrap(True)
        layout.addWidget(self.details_label)

        action_row = QHBoxLayout()
        self.generate_button = QPushButton("إنشاء الفيديو")
        self.generate_button.setObjectName("generateVideoButton")
        self.generate_button.setMinimumHeight(48)
        self.generate_button.clicked.connect(self._create_video)
        action_row.addWidget(self.generate_button, 2)

        self.configure_key_button = QPushButton("إعداد مفتاح Runware")
        self.configure_key_button.setObjectName("configureRunwareKeyButton")
        self.configure_key_button.clicked.connect(self._configure_key)
        action_row.addWidget(self.configure_key_button, 1)
        layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("automaticVideoProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("جاهز.")
        self.progress_label.setObjectName("automaticVideoProgressLabel")
        self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)

        output_row = QHBoxLayout()
        self.view_video_button = QPushButton("عرض الفيديو")
        self.view_video_button.setObjectName("viewVideoButton")
        self.view_video_button.clicked.connect(self._view_video)
        output_row.addWidget(self.view_video_button)

        self.show_location_button = QPushButton("عرض مكانه في الجهاز")
        self.show_location_button.setObjectName("showVideoLocationButton")
        self.show_location_button.clicked.connect(self._show_video_location)
        output_row.addWidget(self.show_location_button)
        output_row.addStretch(1)
        layout.addLayout(output_row)

        review_title = QLabel("التقييم النهائي")
        review_title.setObjectName("sectionTitle")
        layout.addWidget(review_title)

        review_form = QFormLayout()
        self.score_spin = QSpinBox()
        self.score_spin.setObjectName("finalScoreSpinBox")
        self.score_spin.setRange(0, 100)
        self.score_spin.setValue(0)
        self.score_spin.setSuffix(" / 100")
        self.score_spin.setMinimumHeight(38)
        review_form.addRow("درجة المقطع:", self.score_spin)
        layout.addLayout(review_form)

        review_hint = QLabel(
            f"{PASS_THRESHOLD} فأعلى: قبول. أقل من {PASS_THRESHOLD}: "
            "رفض وتجهيز المحاولة التالية تلقائيًا."
        )
        review_hint.setObjectName("muted")
        review_hint.setWordWrap(True)
        layout.addWidget(review_hint)

        self.save_score_button = QPushButton("حفظ التقييم")
        self.save_score_button.setObjectName("saveFinalScoreButton")
        self.save_score_button.setMinimumHeight(42)
        self.save_score_button.clicked.connect(self._save_score)
        layout.addWidget(self.save_score_button)

        layout.addStretch(1)

        footer = QHBoxLayout()
        self.refresh_button = QPushButton("تحديث الحالة")
        self.refresh_button.clicked.connect(self._refresh_state)
        footer.addWidget(self.refresh_button)
        footer.addStretch(1)
        close_button = QPushButton("إغلاق")
        close_button.clicked.connect(self.reject)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    def _stored_api_key(self) -> str | None:
        try:
            return read_runware_api_key()
        except CredentialStoreError as exc:
            self.progress_label.setText(str(exc))
            return None

    def _configure_key(self) -> None:
        value, accepted = QInputDialog.getText(
            self,
            "إعداد مفتاح Runware",
            "ألصق Runware API Key. سيُحفظ في Windows Credential Manager فقط:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return
        try:
            save_runware_api_key(value)
        except CredentialStoreError as exc:
            QMessageBox.critical(self, "تعذر حفظ المفتاح", str(exc))
            return
        QMessageBox.information(
            self,
            "تم حفظ المفتاح",
            "حُفظ المفتاح في Windows Credential Manager، وليس داخل المشروع.",
        )
        self._refresh_state()

    def _ensure_key(self) -> str | None:
        key = self._stored_api_key()
        if key:
            return key
        value, accepted = QInputDialog.getText(
            self,
            "مفتاح Runware مطلوب مرة واحدة",
            "ألصق المفتاح الآن. سيُحفظ بأمان ثم يبدأ التوليد:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return None
        try:
            save_runware_api_key(value)
        except CredentialStoreError as exc:
            QMessageBox.critical(self, "تعذر حفظ المفتاح", str(exc))
            return None
        return value.strip()

    def _refresh_state(self) -> None:
        try:
            spec = load_automatic_video_spec(self.repo_root)
            state = load_state(spec)
            self.last_output = current_output_path(self.repo_root)
        except Exception as exc:
            self.status_label.setText("تعذر قراءة الحالة: " + str(exc))
            self.generate_button.setEnabled(False)
            self.view_video_button.setEnabled(False)
            self.show_location_button.setEnabled(False)
            self.save_score_button.setEnabled(False)
            return

        status = str(state.get("status", "UNKNOWN"))
        attempt = int(state.get("current_attempt", 1))
        maximum = int(state.get("maximum_attempts", 3))
        key_status = (
            "مفتاح Runware محفوظ"
            if self._stored_api_key()
            else "مفتاح Runware غير مضبوط"
        )
        descriptions = {
            "READY_TO_GENERATE":
                f"المحاولة {attempt} من {maximum} جاهزة. اضغط إنشاء الفيديو.",
            "GENERATING":
                f"المحاولة {attempt} قيد التوليد.",
            "RECOVERY_REQUIRED":
                "توجد مهمة سابقة تحتاج استعادة. زر إنشاء الفيديو سيستعيدها "
                "تلقائيًا دون إرسال طلب جديد.",
            "AWAITING_SCORE":
                "اكتمل الفيديو. اعرضه أو افتح مكانه ثم أدخل درجة واحدة.",
            "ACCEPTED":
                "تم قبول المقطع وأصبح جاهزًا للمرحلة التالية.",
            "REQUIRES_PROMPT_REDESIGN":
                "اكتملت المحاولات المتاحة دون قبول. يلزم تصميم Prompt جديد.",
        }
        self.status_label.setText(descriptions.get(status, status))
        self.details_label.setText(
            f"{spec.beat_id} — {spec.model} — "
            f"{spec.width}×{spec.height} — {spec.duration}s — {key_status}"
        )

        running = self.worker is not None and self.worker.isRunning()
        self.generate_button.setEnabled(
            not running
            and status in {
                "READY_TO_GENERATE",
                "RECOVERY_REQUIRED",
            }
        )
        output_ready = (
            self.last_output is not None
            and self.last_output.is_file()
        )
        self.view_video_button.setEnabled(output_ready)
        self.show_location_button.setEnabled(output_ready)
        self.save_score_button.setEnabled(
            not running
            and status == "AWAITING_SCORE"
            and output_ready
        )
        self.score_spin.setEnabled(
            status == "AWAITING_SCORE" and output_ready
        )
        self.configure_key_button.setEnabled(not running)
        self.refresh_button.setEnabled(not running)

    def _create_video(self) -> None:
        key = self._ensure_key()
        if not key:
            return
        self.worker = AutomaticGenerationThread(
            self.repo_root,
            key,
            self,
        )
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.generation_succeeded.connect(self._on_success)
        self.worker.generation_failed.connect(self._on_failure)
        self.worker.finished.connect(self._on_finished)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("بدء العملية التلقائية…")
        self.worker.start()
        self._refresh_state()

    def _on_progress(self, message: str, value: object) -> None:
        self.progress_label.setText(message)
        if isinstance(value, int):
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
        else:
            self.progress_bar.setRange(0, 0)

    def _on_success(self, result: object) -> None:
        if not isinstance(result, AutomaticVideoResult):
            self._on_failure("INVALID_AUTOMATIC_VIDEO_RESULT")
            return
        self.last_output = result.output_path
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        cost = (
            f"${result.actual_cost_usd:.4f}"
            if result.actual_cost_usd is not None
            else "غير متاحة"
        )
        self.progress_label.setText(
            f"اكتمل الفيديو. المحاولة {result.attempt_number}، "
            f"التكلفة {cost}."
        )
        self._refresh_state()

    def _on_failure(self, error: str) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("توقفت العملية: " + error)
        QMessageBox.critical(
            self,
            "تعذر إنشاء الفيديو",
            error
            + "\n\nاضغط إنشاء الفيديو لاحقًا؛ سيستعيد سراج المهمة نفسها "
            "عند وجود قفل، ولن يكرر الإرسال.",
        )
        self._refresh_state()

    def _on_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = None
        self._refresh_state()

    def _view_video(self) -> None:
        if self.last_output is None or not self.last_output.is_file():
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.last_output))
        )

    def _show_video_location(self) -> None:
        if self.last_output is None or not self.last_output.is_file():
            return
        native = QDir.toNativeSeparators(str(self.last_output))
        if os.name == "nt":
            QProcess.startDetached(
                "explorer.exe",
                ["/select,", native],
            )
        else:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.last_output.parent))
            )

    def _save_score(self) -> None:
        score = self.score_spin.value()
        try:
            review = save_final_score(self.repo_root, score)
        except ProductionGateError as exc:
            QMessageBox.critical(self, "تعذر حفظ التقييم", str(exc))
            return

        decision = str(review["decision"])
        if decision == "PASS":
            message = (
                f"تم حفظ {score}/100 وقبول المقطع. "
                "سراج جاهز لبناء المرحلة التالية."
            )
        else:
            message = (
                f"تم حفظ {score}/100 ورفض المقطع. "
                "تم تجهيز المحاولة التالية؛ اضغط إنشاء الفيديو."
            )
        QMessageBox.information(self, "تم حفظ التقييم", message)
        self.score_spin.setValue(0)
        self._refresh_state()

    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self,
                "التوليد مستمر",
                "اترك النافذة مفتوحة حتى تنتهي العملية بأمان.",
            )
            return
        super().reject()
