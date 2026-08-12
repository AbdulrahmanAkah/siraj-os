"""SIRAJ Production Studio V6.4 — one-click Autopilot UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.presentation.desktop.production_studio_v6_0_1 import ProductionStudioV601Window
from src.application.siraj_series_autopilot_v6_0_1 import STAGES, stage_graph
from src.application.siraj_production_composition_root import (
    authorize_current_stage,
    authorization_phrase_for,
    inspect_autopilot,
    run_until_gate,
)
from src.application.provider_credentials_v1 import (
    read_elevenlabs_api_key,
    read_openai_api_key,
)
from src.application.windows_credentials_v1 import (
    CredentialStoreError,
    read_runware_api_key,
    save_runware_api_key,
)


class AutopilotWorkerV64(QThread):
    progress_changed = Signal(str, int, int, str)
    finished_with_result = Signal(object)
    failed = Signal(str)

    def __init__(self, repo_root: Path, parent=None):
        super().__init__(parent)
        self.repo_root = repo_root

    def run(self):
        try:
            result = run_until_gate(
                self.repo_root,
                progress=lambda stage, done, total, action: self.progress_changed.emit(
                    stage, int(done), int(total), str(action)
                ),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_with_result.emit(result)


class PaidAuthorizationDialogV64(QDialog):
    def __init__(self, stage: str, phrase: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تفويض عملية مدفوعة — سراج")
        self.setMinimumWidth(650)
        self.confirmed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        title = QLabel("تفويض صريح قبل العملية المدفوعة")
        title.setObjectName("EpisodeTitle")
        root.addWidget(title)

        details = QLabel(
            f"المرحلة: {stage}\n"
            "لا توجد إعادة محاولة مدفوعة تلقائية.\n"
            "إذا فشل المزود أو أصبحت النتيجة مجهولة، سيتوقف سراج ويطلب "
            "تفويضًا جديدًا قبل أي محاولة أخرى."
        )
        details.setWordWrap(True)
        details.setObjectName("StatusBadgeWarn")
        root.addWidget(details)

        root.addWidget(QLabel("اكتب العبارة التالية حرفيًا للمتابعة:"))
        phrase_label = QLabel(phrase)
        phrase_label.setObjectName("GoldValue")
        phrase_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(phrase_label)

        self.input = QLineEdit()
        self.input.setPlaceholderText("عبارة التفويض")
        root.addWidget(self.input)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("إلغاء")
        cancel.clicked.connect(self.reject)
        self.confirm = QPushButton("تفويض ومتابعة")
        self.confirm.setObjectName("PrimaryButton")
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self._accept)
        actions.addWidget(cancel)
        actions.addWidget(self.confirm)
        root.addLayout(actions)

        self.input.textChanged.connect(
            lambda value: self.confirm.setEnabled(value.strip() == phrase)
        )

    def _accept(self):
        self.confirmed = True
        self.accept()


class ProductionStudioV64Window(ProductionStudioV601Window):
    def __init__(self, repo_root: Path):
        self.autopilot_worker_v64 = None
        super().__init__(repo_root)
        self.setWindowTitle("سراج — Production Studio V6.4 One-Click Autopilot")

        self.autopilot_progress = QProgressBar()
        self.autopilot_progress.setRange(0, len(STAGES))
        self.autopilot_page.layout().insertWidget(3, self.autopilot_progress)

        self.autopilot_log = QPlainTextEdit()
        self.autopilot_log.setReadOnly(True)
        self.autopilot_log.setMaximumBlockCount(3000)
        self.autopilot_log.setPlaceholderText("سجل Autopilot سيظهر هنا.")
        self.autopilot_page.layout().addWidget(self.autopilot_log, 1)

        self.autopilot_button.clicked.disconnect()
        self.autopilot_button.clicked.connect(self._start_autopilot_v64)
        self.reaudit_button.clicked.disconnect()
        self.reaudit_button.clicked.connect(self.refresh_autopilot)
        self.reaudit_button.setText("تحديث حالة Autopilot")
        self.refresh_autopilot()

    def _append_log(self, text: str):
        self.autopilot_log.appendPlainText(text)

    def _ensure_runware_credential(self) -> bool:
        try:
            if read_runware_api_key():
                return True
        except Exception as exc:
            QMessageBox.critical(self, "Runware Credential", str(exc))
            return False

        dialog = QDialog(self)
        dialog.setWindowTitle("مفتاح Runware")
        dialog.setMinimumWidth(620)
        root = QVBoxLayout(dialog)
        info = QLabel(
            "أدخل Runware API Key محليًا. سيُحفظ في Windows Credential Manager "
            "تحت SIRAJ/RUNWARE_API_KEY ولن يظهر في سجل سراج."
        )
        info.setWordWrap(True)
        root.addWidget(info)
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        root.addWidget(field)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("إلغاء")
        cancel.clicked.connect(dialog.reject)
        save = QPushButton("حفظ محليًا")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(dialog.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            save_runware_api_key(field.text())
        except CredentialStoreError as exc:
            QMessageBox.critical(self, "فشل حفظ Runware Key", str(exc))
            return False
        finally:
            field.setText("")
        return True

    def _check_credential_for_stage(self, stage: str) -> bool:
        luna = {
            "TOPIC_SELECTION",
            "SOURCE_RESEARCH_FROM_ZERO",
            "SOURCE_CLAIM_MATRIX",
            "STORY_ARCHITECTURE",
            "ICONIC_CINEMATIC_REVIEW",
            "FINAL_SCRIPT",
            "PRONUNCIATION_AND_PERFORMANCE_GATE",
            "AUDIO_BOUND_STORYBOARD",
            "LUNA_SEMANTIC_PROMPT_DIRECTION",
            "NARRATION_VISUAL_ALIGNMENT_GATE",
            "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
        }
        try:
            if stage in luna:
                if read_openai_api_key():
                    return True
                QMessageBox.warning(self, "OpenAI Key", "مفتاح OpenAI غير موجود في Credential Manager.")
                return False
            if stage == "FINAL_TTS":
                if read_elevenlabs_api_key():
                    return True
                QMessageBox.warning(self, "ElevenLabs Key", "مفتاح ElevenLabs غير موجود في Credential Manager.")
                return False
            if stage == "PROVIDER_EXECUTION":
                return self._ensure_runware_credential()
        except Exception as exc:
            QMessageBox.critical(self, "Credential Error", str(exc))
            return False
        return True

    def _authorize_gate_and_continue(self):
        inspection = inspect_autopilot(self.repo_root)
        if not (inspection.paid_stage and not inspection.authorized):
            self._launch_worker()
            return

        if not self._check_credential_for_stage(inspection.stage):
            self.refresh_autopilot()
            return

        stage, phrase = authorization_phrase_for(self.repo_root)
        dialog = PaidAuthorizationDialogV64(stage, phrase, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.confirmed:
            self._append_log(f"توقف عند بوابة التفويض: {stage}")
            self.refresh_autopilot()
            return

        try:
            authorize_current_stage(self.repo_root, phrase)
        except Exception as exc:
            QMessageBox.critical(self, "فشل التفويض", str(exc))
            self.refresh_autopilot()
            return

        self._append_log(f"تم تفويض المرحلة: {stage}")
        self._launch_worker()

    def _start_autopilot_v64(self):
        if self.autopilot_worker_v64 is not None and self.autopilot_worker_v64.isRunning():
            return
        try:
            inspection = inspect_autopilot(self.repo_root)
        except Exception as exc:
            QMessageBox.critical(self, "Autopilot", str(exc))
            return

        if inspection.terminal:
            QMessageBox.information(self, "جاهزة للمراجعة", "الحلقة وصلت إلى READY_FOR_FINAL_HUMAN_REVIEW.")
            return
        if inspection.paid_stage and not inspection.authorized:
            self._authorize_gate_and_continue()
        else:
            self._launch_worker()

    def _launch_worker(self):
        self.autopilot_button.setEnabled(False)
        self.reaudit_button.setEnabled(False)
        worker = AutopilotWorkerV64(self.repo_root, self)
        self.autopilot_worker_v64 = worker
        worker.progress_changed.connect(self._on_autopilot_progress)
        worker.finished_with_result.connect(self._on_autopilot_result)
        worker.failed.connect(self._on_autopilot_failed)
        worker.finished.connect(self._worker_cleanup)
        worker.start()

    def _worker_cleanup(self):
        self.autopilot_button.setEnabled(True)
        self.reaudit_button.setEnabled(True)
        self.refresh_autopilot()

    def _on_autopilot_progress(self, stage: str, done: int, total: int, action: str):
        self.autopilot_progress.setMaximum(total)
        self.autopilot_progress.setValue(done)
        self._append_log(f"[{done}/{total}] {stage} — {action}")

    def _on_autopilot_result(self, result):
        self._append_log(f"{result.status}: {result.stage}")
        if result.status == "PAID_AUTHORIZATION_REQUIRED":
            self.refresh_autopilot()
            self._authorize_gate_and_continue()
            return
        if result.status == "READY_FOR_FINAL_HUMAN_REVIEW":
            QMessageBox.information(
                self,
                "سراج",
                "اكتمل الإنتاج الآلي. الحلقة جاهزة للمشاهدة والمراجعة البشرية النهائية. النشر لم يتم تلقائيًا.",
            )

    def _on_autopilot_failed(self, error: str):
        self._append_log("STOPPED: " + error)
        QMessageBox.critical(self, "توقف Autopilot", error)

    def refresh_autopilot(self):
        try:
            inspection = inspect_autopilot(self.repo_root)
        except Exception as exc:
            try:
                self.resume_banner.setText("تعذر قراءة حالة Autopilot: " + str(exc))
                self.autopilot_button.setEnabled(False)
            except Exception:
                pass
            return

        if inspection.episode_id == "NEXT_NEW_EPISODE":
            self.resume_banner.setText(
                "لا توجد حلقة غير مكتملة.\nالحلقة الجديدة ستبدأ تلقائيًا من TOPIC_SELECTION."
            )
        else:
            self.resume_banner.setText(
                f"الحلقة النشطة: {inspection.episode_id}\n"
                f"المرحلة التالية: {inspection.stage}\n"
                "المراحل المكتملة محمية من إعادة التشغيل."
            )

        if inspection.terminal:
            self.autopilot_status.setText(
                "READY_FOR_FINAL_HUMAN_REVIEW\nالإنتاج الآلي انتهى. بقيت المشاهدة البشرية والنشر اليدوي."
            )
            self.autopilot_button.setText("الحلقة جاهزة للمراجعة البشرية")
            self.autopilot_button.setEnabled(False)
        elif inspection.paid_stage and not inspection.authorized:
            self.autopilot_status.setText(
                "بوابة مدفوعة بانتظار تفويضك الصريح:\n"
                + inspection.stage
                + "\nلن يحدث أي دفع قبل التفويض."
            )
            self.autopilot_button.setText("تفويض المرحلة ومتابعة Autopilot")
            self.autopilot_button.setEnabled(True)
        else:
            self.autopilot_status.setText("Autopilot جاهز من المرحلة:\n" + inspection.stage)
            self.autopilot_button.setText("ابدأ / استأنف الإنتاج التلقائي")
            self.autopilot_button.setEnabled(True)

        self.autopilot_progress.setMaximum(len(STAGES))
        self.autopilot_progress.setValue(len(inspection.completed_stages))

        graph = stage_graph()
        self.stage_table.setRowCount(len(graph))
        for row, stage_info in enumerate(graph):
            stage = stage_info["stage"]
            if stage in inspection.completed_stages:
                episode_state = "مكتمل — محمي"
            elif stage == inspection.stage:
                episode_state = "بوابة تفويض" if inspection.paid_stage and not inspection.authorized else "المرحلة التالية"
            elif stage == "READY_FOR_FINAL_HUMAN_REVIEW":
                episode_state = "الهدف النهائي"
            else:
                episode_state = "لاحق"
            backend = "Human Gate" if stage == "READY_FOR_FINAL_HUMAN_REVIEW" else "V6 Certified"
            values = [str(stage_info["index"]), stage, episode_state, stage_info["kind"], backend]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col in {0, 2, 3, 4}:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.stage_table.setItem(row, col, cell)


def launch_production_studio_v6_4(repo_root: Path) -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("SIRAJ Production Studio V6.4")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    window = ProductionStudioV64Window(repo_root.resolve())
    window.show()
    return app.exec()
