from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.application.runware_execution_v1 import (
    ExecutionResult,
    ProductionGateError,
    execute_once,
    load_execution_spec,
    read_execution_state,
    recover_existing,
    save_human_review,
)

PRODUCTION_CONSOLE_RELEASE = "SIRAJ_DESKTOP_PRODUCTION_CONSOLE_V1"


class RunwareExecutionThread(QThread):
    progress_changed = Signal(str, object)
    execution_succeeded = Signal(object)
    execution_failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        api_key: str,
        *,
        recover: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root
        self._api_key = api_key
        self.recover = recover

    def run(self) -> None:
        def progress(message: str, value: int | None) -> None:
            self.progress_changed.emit(message, value)

        try:
            runner = recover_existing if self.recover else execute_once
            result = runner(
                self.repo_root,
                self._api_key,
                progress=progress,
            )
        except Exception as exc:
            self.execution_failed.emit(str(exc))
        else:
            self.execution_succeeded.emit(result)
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
        self.spec = None
        self.worker: RunwareExecutionThread | None = None
        self.last_result: ExecutionResult | None = None
        self.setObjectName("productionConsoleDialog")
        self.setWindowTitle("سراج — وحدة الإنتاج الفعلي — Beat 01")
        self.resize(1050, 760)
        self.setMinimumSize(900, 650)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()
        self._run_preflight()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(10)

        title = QLabel("وحدة الإنتاج الفعلي — حلقة آدم")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "تنفيذ مقيد لمحاولة Runware واحدة فقط للـBeat المعتمد، "
            "ثم مراجعة النتيجة خارج الواجهة وتسجيل القرار هنا."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("productionConsoleTabs")
        self.tabs.addTab(self._build_package_tab(), "حزمة التنفيذ")
        self.tabs.addTab(self._build_execution_tab(), "التنفيذ")
        self.tabs.addTab(self._build_review_tab(), "المراجعة")
        outer.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.preflight_button = QPushButton("إعادة فحص الجاهزية")
        self.preflight_button.clicked.connect(self._run_preflight)
        footer.addWidget(self.preflight_button)
        footer.addStretch(1)
        close_button = QPushButton("إغلاق")
        close_button.clicked.connect(self.reject)
        footer.addWidget(close_button)
        outer.addLayout(footer)

    def _scroll_host(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setWidget(content)
        return scroll

    def _build_package_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)

        form = QFormLayout()
        self.package_fields: dict[str, QLabel] = {}
        for key, caption in (
            ("episode", "الحلقة"),
            ("shot", "اللقطة"),
            ("beat", "وحدة التوليد"),
            ("model", "النموذج"),
            ("dimensions", "الدقة"),
            ("duration", "المدة"),
            ("seed", "Seed"),
            ("cost", "سقف التكلفة"),
            ("package_hash", "بصمة الحزمة"),
            ("authorization", "الاعتماد"),
        ):
            label = QLabel("—")
            label.setObjectName("muted")
            label.setWordWrap(True)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.package_fields[key] = label
            form.addRow(caption + ":", label)
        layout.addLayout(form)

        prompt_title = QLabel("Prompt النهائي")
        prompt_title.setObjectName("sectionTitle")
        layout.addWidget(prompt_title)
        self.prompt_view = QPlainTextEdit()
        self.prompt_view.setObjectName("productionPromptView")
        self.prompt_view.setReadOnly(True)
        self.prompt_view.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
        )
        self.prompt_view.setMinimumHeight(280)
        layout.addWidget(self.prompt_view)

        buttons = QHBoxLayout()
        copy_prompt = QPushButton("نسخ Prompt")
        copy_prompt.clicked.connect(self._copy_prompt)
        buttons.addWidget(copy_prompt)
        copy_settings = QPushButton("نسخ إعدادات التنفيذ")
        copy_settings.clicked.connect(self._copy_settings)
        buttons.addWidget(copy_settings)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return self._scroll_host(content)

    def _build_execution_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(9)

        self.gate_status = QLabel("لم يُفحص بعد")
        self.gate_status.setObjectName("executionGateStatus")
        self.gate_status.setWordWrap(True)
        layout.addWidget(self.gate_status)

        key_form = QFormLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setObjectName("runwareApiKeyInput")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText(
            "ألصق المفتاح هنا أو استخدم RUNWARE_API_KEY من البيئة"
        )
        self.api_key_input.setClearButtonEnabled(True)
        self.api_key_input.textChanged.connect(self._update_action_state)
        key_form.addRow("Runware API Key:", self.api_key_input)
        layout.addLayout(key_form)

        self.environment_key_status = QLabel("")
        self.environment_key_status.setObjectName("muted")
        layout.addWidget(self.environment_key_status)

        self.confirmation = QCheckBox(
            "أؤكد تنفيذ محاولة مدفوعة واحدة فقط للـBeat 01، "
            "بحد أقصى مصرح به 0.40 دولار، دون إعادة محاولة تلقائية."
        )
        self.confirmation.setObjectName("paidExecutionConfirmation")
        self.confirmation.setMinimumHeight(44)
        self.confirmation.toggled.connect(self._update_action_state)
        layout.addWidget(self.confirmation)

        warning = QLabel(
            "بمجرد الضغط على التنفيذ يُنشأ قفل دائم قبل الاتصال بالشبكة. "
            "أي انقطاع أو خطأ لا يسمح بإرسال طلب جديد؛ يمكن فقط استعادة "
            "المهمة نفسها عبر taskUUID."
        )
        warning.setObjectName("muted")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        action_row = QHBoxLayout()
        self.execute_button = QPushButton("تنفيذ Beat 01 الآن")
        self.execute_button.setObjectName("executeBeat01Button")
        self.execute_button.clicked.connect(self._start_execution)
        action_row.addWidget(self.execute_button)

        self.recover_button = QPushButton("استعادة المهمة القائمة")
        self.recover_button.setObjectName("recoverBeat01Button")
        self.recover_button.clicked.connect(self._start_recovery)
        action_row.addWidget(self.recover_button)

        self.open_output_button = QPushButton("فتح الفيديو الناتج")
        self.open_output_button.setObjectName("openGeneratedVideoButton")
        self.open_output_button.clicked.connect(self._open_output)
        action_row.addWidget(self.open_output_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("productionProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.progress_text = QLabel("جاهز للفحص.")
        self.progress_text.setObjectName("productionProgressText")
        self.progress_text.setWordWrap(True)
        layout.addWidget(self.progress_text)

        self.execution_log = QPlainTextEdit()
        self.execution_log.setObjectName("productionExecutionLog")
        self.execution_log.setReadOnly(True)
        self.execution_log.setMinimumHeight(240)
        layout.addWidget(self.execution_log, 1)
        return content

    def _score_spin(self, maximum: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, maximum)
        spin.valueChanged.connect(self._update_review_total)
        return spin

    def _build_review_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)

        guidance = QLabel(
            "شاهد الفيديو خارج الواجهة، ثم سجّل التقييم هنا. "
            "أي عيب مانع يجعل القرار FAIL مهما كانت الدرجة."
        )
        guidance.setObjectName("muted")
        guidance.setWordWrap(True)
        layout.addWidget(guidance)

        form = QFormLayout()
        self.review_scores = {
            "material_transformation": self._score_spin(25),
            "water_clay_physics": self._score_spin(25),
            "camera_composition": self._score_spin(15),
            "temporal_stability": self._score_spin(15),
            "visual_safety": self._score_spin(20),
        }
        captions = {
            "material_transformation": "تحول المادة والوظيفة السردية /25",
            "water_clay_physics": "فيزياء الماء والطين /25",
            "camera_composition": "الكاميرا والتكوين /15",
            "temporal_stability": "الثبات الزمني والهندسي /15",
            "visual_safety": "السلامة البصرية /20",
        }
        for key, spin in self.review_scores.items():
            form.addRow(captions[key] + ":", spin)
        layout.addLayout(form)

        self.review_total = QLabel("المجموع: 0/100 — FAIL")
        self.review_total.setObjectName("reviewTotalLabel")
        layout.addWidget(self.review_total)

        self.blocking_failures = QPlainTextEdit()
        self.blocking_failures.setPlaceholderText(
            "العيوب المانعة، سطر لكل عيب. اتركه فارغًا عند عدم وجودها."
        )
        self.blocking_failures.setMaximumHeight(100)
        self.blocking_failures.textChanged.connect(self._update_review_total)
        layout.addWidget(QLabel("العيوب المانعة"))
        layout.addWidget(self.blocking_failures)

        self.camera_notes = QPlainTextEdit()
        self.camera_notes.setPlaceholderText("ملاحظات الكاميرا والتكوين")
        self.camera_notes.setMaximumHeight(75)
        layout.addWidget(self.camera_notes)

        self.material_notes = QPlainTextEdit()
        self.material_notes.setPlaceholderText("ملاحظات فيزياء الماء والطين")
        self.material_notes.setMaximumHeight(75)
        layout.addWidget(self.material_notes)

        self.stability_notes = QPlainTextEdit()
        self.stability_notes.setPlaceholderText("ملاحظات الثبات الزمني والهندسي")
        self.stability_notes.setMaximumHeight(75)
        layout.addWidget(self.stability_notes)

        self.save_review_button = QPushButton("حفظ المراجعة البشرية")
        self.save_review_button.setObjectName("saveBeat01ReviewButton")
        self.save_review_button.clicked.connect(self._save_review)
        layout.addWidget(self.save_review_button)
        return self._scroll_host(content)

    def _api_key(self) -> str:
        typed = self.api_key_input.text().strip()
        if typed:
            return typed
        return os.environ.get("RUNWARE_API_KEY", "").strip()

    def _run_preflight(self) -> None:
        try:
            self.spec = load_execution_spec(self.repo_root)
            state = read_execution_state(self.spec)
        except Exception as exc:
            self.spec = None
            self.gate_status.setText(f"فشل فحص الجاهزية: {exc}")
            self.execution_log.appendPlainText(f"PREFLIGHT_FAIL {exc}")
            self._update_action_state()
            return

        spec = self.spec
        self.package_fields["episode"].setText(spec.episode_id)
        self.package_fields["shot"].setText(spec.shot_id)
        self.package_fields["beat"].setText(spec.beat_id)
        self.package_fields["model"].setText(spec.model)
        self.package_fields["dimensions"].setText(
            f"{spec.width}×{spec.height}"
        )
        self.package_fields["duration"].setText(f"{spec.duration} ثوانٍ")
        self.package_fields["seed"].setText(str(spec.seed))
        self.package_fields["cost"].setText(
            f"≤ ${spec.max_cost_usd:.2f}"
        )
        self.package_fields["package_hash"].setText(spec.package_sha256)
        self.package_fields["authorization"].setText(
            "معتمد لمحاولة سطح مكتب واحدة فقط"
        )
        self.prompt_view.setPlainText(spec.positive_prompt)

        env_present = bool(os.environ.get("RUNWARE_API_KEY", "").strip())
        self.environment_key_status.setText(
            "RUNWARE_API_KEY موجود في البيئة ولن يُعرض أو يُحفظ."
            if env_present
            else "لا يوجد مفتاح في البيئة؛ يمكن لصقه في الحقل أعلاه."
        )

        receipt = state.get("receipt")
        review = state.get("review")
        if isinstance(receipt, dict) and str(
            receipt.get("status", "")
        ).startswith("SUCCESS"):
            self.gate_status.setText(
                "تم توليد Beat 01 وتسجيل الإيصال والبصمة. "
                "المرحلة الحالية: المراجعة البشرية."
            )
            relative = receipt.get("output_path_relative")
            if isinstance(relative, str):
                path = self.repo_root / relative
                if path.is_file():
                    self.last_result = ExecutionResult(
                        task_uuid=str(receipt.get("task_uuid", "")),
                        video_uuid=str(receipt.get("video_uuid", "")),
                        video_url=str(receipt.get("video_url", "")),
                        output_path=path,
                        output_sha256=str(receipt.get("output_sha256", "")),
                        returned_seed=receipt.get("returned_seed"),
                        actual_cost_usd=receipt.get("actual_cost_usd"),
                        receipt_path=spec.receipt_path,
                        status=str(receipt.get("status")),
                    )
            self.execution_log.appendPlainText("PREFLIGHT GENERATED")
        elif state.get("lock_exists"):
            lock = state.get("lock") or {}
            self.gate_status.setText(
                "توجد محاولة مقفلة بالفعل. لا يمكن إنشاء طلب جديد؛ "
                "استخدم استعادة المهمة القائمة."
            )
            self.execution_log.appendPlainText(
                "PREFLIGHT LOCKED "
                + str(lock.get("status", "UNKNOWN"))
            )
        else:
            self.gate_status.setText(
                "PASS — الحزمة والاعتماد والبصمة صحيحة. "
                "لا يوجد طلب سابق."
            )
            self.execution_log.appendPlainText(
                "PREFLIGHT PASS EXACTLY_ONE_SUBMISSION"
            )

        if isinstance(review, dict):
            self.execution_log.appendPlainText(
                "HUMAN_REVIEW "
                + str(review.get("human_decision", "UNKNOWN"))
                + " SCORE="
                + str(review.get("score_total", "—"))
            )
        self._update_action_state()

    def _update_action_state(self) -> None:
        spec_ready = self.spec is not None
        state: dict[str, Any] = {}
        if spec_ready:
            try:
                state = read_execution_state(self.spec)
            except Exception:
                state = {}
        key_present = bool(self._api_key())
        confirmed = self.confirmation.isChecked()
        running = self.worker is not None and self.worker.isRunning()
        lock_exists = bool(state.get("lock_exists"))
        receipt = state.get("receipt")
        success = (
            isinstance(receipt, dict)
            and str(receipt.get("status", "")).startswith("SUCCESS")
        )
        self.execute_button.setEnabled(
            spec_ready
            and key_present
            and confirmed
            and not running
            and not lock_exists
            and not success
        )
        self.recover_button.setEnabled(
            spec_ready
            and key_present
            and confirmed
            and not running
            and lock_exists
            and not success
        )
        self.open_output_button.setEnabled(
            self.last_result is not None
            and self.last_result.output_path.is_file()
        )
        self.save_review_button.setEnabled(success and not running)
        self.preflight_button.setEnabled(not running)

    def _copy_prompt(self) -> None:
        QGuiApplication.clipboard().setText(self.prompt_view.toPlainText())

    def _copy_settings(self) -> None:
        if self.spec is None:
            return
        text = (
            f"taskType=videoInference\n"
            f"model={self.spec.model}\n"
            f"width={self.spec.width}\n"
            f"height={self.spec.height}\n"
            f"duration={self.spec.duration}\n"
            f"seed={self.spec.seed}\n"
            f"numberResults=1\n"
            f"outputFormat=MP4\n"
            f"generateAudio=false\n"
            f"personGeneration=dont_allow\n"
            f"maximumAuthorisedCostUSD={self.spec.max_cost_usd:.2f}"
        )
        QGuiApplication.clipboard().setText(text)

    def _start_execution(self) -> None:
        if self.spec is None:
            return
        answer = QMessageBox.warning(
            self,
            "تأكيد محاولة Runware المدفوعة",
            "سيتم إرسال طلب videoInference واحد فقط:\n\n"
            f"{self.spec.beat_id}\n"
            f"{self.spec.model}\n"
            f"{self.spec.duration}s — "
            f"{self.spec.width}×{self.spec.height}\n"
            f"سقف التكلفة المصرح: ${self.spec.max_cost_usd:.2f}\n\n"
            "سيُنشأ قفل دائم قبل الاتصال، ولن تحدث إعادة محاولة تلقائية.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_worker(recover=False)

    def _start_recovery(self) -> None:
        self._start_worker(recover=True)

    def _start_worker(self, *, recover: bool) -> None:
        key = self._api_key()
        if not key:
            QMessageBox.critical(self, "المفتاح مفقود", "أدخل Runware API Key.")
            return
        self.progress_bar.setValue(0)
        self.progress_text.setText(
            "استعادة المهمة القائمة…" if recover else "بدء التنفيذ…"
        )
        self.execution_log.appendPlainText(
            "RECOVERY_START" if recover else "PAID_SUBMISSION_START"
        )
        self.worker = RunwareExecutionThread(
            self.repo_root,
            key,
            recover=recover,
            parent=self,
        )
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.execution_succeeded.connect(self._on_success)
        self.worker.execution_failed.connect(self._on_failure)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()
        self.api_key_input.clear()
        self._update_action_state()

    def _on_progress(self, message: str, value: object) -> None:
        self.progress_text.setText(message)
        self.execution_log.appendPlainText(message)
        if isinstance(value, int):
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
        else:
            self.progress_bar.setRange(0, 0)

    def _on_success(self, result: object) -> None:
        if not isinstance(result, ExecutionResult):
            self._on_failure("INVALID_EXECUTION_RESULT")
            return
        self.last_result = result
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        cost = (
            f"${result.actual_cost_usd:.4f}"
            if result.actual_cost_usd is not None
            else "غير متاح"
        )
        self.progress_text.setText(
            f"تم التوليد والتنزيل. التكلفة: {cost}"
        )
        self.execution_log.appendPlainText(
            "EXECUTION_SUCCESS "
            + result.output_path.name
            + " SHA256="
            + result.output_sha256
        )
        QMessageBox.information(
            self,
            "اكتمل Beat 01",
            "تم تنزيل الفيديو وتسجيل الإيصال والبصمة.\n"
            "افتح الملف وراجعه خارج الواجهة، ثم سجّل التقييم في تبويب المراجعة.",
        )
        self.tabs.setCurrentIndex(2)
        self._run_preflight()

    def _on_failure(self, error: str) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_text.setText("توقف التنفيذ: " + error)
        self.execution_log.appendPlainText("EXECUTION_FAIL " + error)
        QMessageBox.critical(
            self,
            "توقف التنفيذ",
            error
            + "\n\nلا تُرسل محاولة جديدة. استخدم الاستعادة عند وجود taskUUID.",
        )
        self._run_preflight()

    def _on_worker_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = None
        self._update_action_state()

    def _open_output(self) -> None:
        if self.last_result is None:
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.last_result.output_path))
        )

    def _update_review_total(self) -> None:
        total = sum(spin.value() for spin in self.review_scores.values())
        blockers = bool(self.blocking_failures.toPlainText().strip())
        decision = "PASS" if total >= 80 and not blockers else "FAIL"
        self.review_total.setText(
            f"المجموع: {total}/100 — {decision}"
        )

    def _save_review(self) -> None:
        scores = {
            key: spin.value()
            for key, spin in self.review_scores.items()
        }
        notes = {
            "camera_notes": self.camera_notes.toPlainText(),
            "material_physics_notes": self.material_notes.toPlainText(),
            "temporal_stability_notes": self.stability_notes.toPlainText(),
        }
        try:
            review = save_human_review(
                self.repo_root,
                scores,
                self.blocking_failures.toPlainText(),
                notes,
            )
        except ProductionGateError as exc:
            QMessageBox.critical(self, "تعذر حفظ المراجعة", str(exc))
            return
        decision = str(review["human_decision"])
        QMessageBox.information(
            self,
            "تم حفظ المراجعة",
            f"القرار: {decision}\n"
            f"الدرجة: {review['score_total']}/100\n"
            f"المرحلة التالية: {review['next_stage']}",
        )
        self.execution_log.appendPlainText(
            f"REVIEW_SAVED {decision} SCORE={review['score_total']}"
        )
        self._run_preflight()

    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self,
                "التنفيذ مستمر",
                "اترك النافذة مفتوحة حتى يكتمل التوليد أو يتوقف بأمان.",
            )
            return
        super().reject()
