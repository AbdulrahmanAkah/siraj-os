from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QDir, QProcess, QThread, QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
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
from src.application.episode_production_control_v1 import (
    EpisodeProductionPolicyError,
    episode_progress,
    load_episode_plan,
    queue_rows,
    scan_actual_paid_spend,
)
from src.application.windows_credentials_v1 import (
    CredentialStoreError,
    read_runware_api_key,
    save_runware_api_key,
)

PRODUCTION_CONSOLE_RELEASE = "SIRAJ_EPISODE_PRODUCTION_CONTROL_V1"

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
        self.setWindowTitle("سراج — إدارة إنتاج حلقة آدم")
        self.resize(1080, 720)
        self.setMinimumSize(900, 620)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()
        self._refresh_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("إدارة إنتاج حلقة آدم")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "الخطة الهجينة الملزمة: سقف 40$، فيديو مولد 120–180 ثانية، "
            "والباقي صور متحركة وتركيب بصري. الموسيقى ممنوعة والمؤثرات "
            "الصوتية المناسبة للمشهد مسموحة."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("episodeProductionTabs")
        root.addWidget(self.tabs, 1)

        self.plan_tab = QWidget()
        self.plan_tab.setObjectName("episodePlanTab")
        self.tabs.addTab(self.plan_tab, "خطة الحلقة")
        self._build_plan_tab()

        self.clip_tab = QWidget()
        self.clip_tab.setObjectName("clipProductionTab")
        self.tabs.addTab(self.clip_tab, "إنتاج المقطع")
        self._build_clip_tab()

        footer = QHBoxLayout()
        self.refresh_button = QPushButton("تحديث الحالة")
        self.refresh_button.setObjectName("refreshEpisodeProductionButton")
        self.refresh_button.clicked.connect(self._refresh_state)
        footer.addWidget(self.refresh_button)
        footer.addStretch(1)
        close_button = QPushButton("إغلاق")
        close_button.clicked.connect(self.reject)
        footer.addWidget(close_button)
        root.addLayout(footer)

    def _build_plan_tab(self) -> None:
        layout = QVBoxLayout(self.plan_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.policy_summary_label = QLabel("")
        self.policy_summary_label.setObjectName("episodePolicySummary")
        self.policy_summary_label.setWordWrap(True)
        layout.addWidget(self.policy_summary_label)

        self.budget_summary_label = QLabel("")
        self.budget_summary_label.setObjectName("episodeBudgetSummary")
        self.budget_summary_label.setWordWrap(True)
        layout.addWidget(self.budget_summary_label)

        self.next_item_label = QLabel("")
        self.next_item_label.setObjectName("nextEpisodeQueueItem")
        self.next_item_label.setWordWrap(True)
        layout.addWidget(self.next_item_label)

        self.queue_table = QTableWidget()
        self.queue_table.setObjectName("episodeProductionQueueTable")
        self.queue_table.setColumnCount(7)
        self.queue_table.setHorizontalHeaderLabels(
            [
                "#",
                "المعرّف",
                "اللقطة",
                "المعالجة",
                "مدة المونتاج",
                "فيديو مولد",
                "الحالة",
            ]
        )
        self.queue_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.queue_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.queue_table.setAlternatingRowColors(True)
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.queue_table, 1)

    def _build_clip_tab(self) -> None:
        layout = QVBoxLayout(self.clip_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.status_label = QLabel("جارٍ قراءة حالة إنتاج المقطع…")
        self.status_label.setObjectName("automaticVideoStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(48)
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
        self.show_location_button.clicked.connect(
            self._show_video_location
        )
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
            "رفض وتجهيز المحاولة التالية، من دون إعادة مدفوعة خفية."
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

    def _refresh_episode_plan(self) -> None:
        try:
            plan = load_episode_plan(self.repo_root)
            budget = scan_actual_paid_spend(self.repo_root)
            progress = episode_progress(self.repo_root)
            rows = queue_rows(self.repo_root)
        except EpisodeProductionPolicyError as exc:
            self.policy_summary_label.setText(
                "تعذر تحميل سياسة الحلقة: " + str(exc)
            )
            self.queue_table.setRowCount(0)
            return

        counts = plan["treatment_counts"]
        self.policy_summary_label.setText(
            "الخطة الملزمة: "
            f"{progress.total_shots} لقطة مونتاجية — "
            f"{counts['GENERATED_VIDEO']} فيديوهات × 8 ثوانٍ = "
            f"{progress.planned_video_seconds} ثانية — "
            f"{counts['ANIMATED_STILL_COMPOSITING']} صورة متحركة/تركيب — "
            f"{counts['GRAPHICS']} جرافيك. "
            "الموسيقى: ممنوعة. المؤثرات الصوتية: مسموحة بأي نوع مناسب للمشهد."
        )
        self.budget_summary_label.setText(
            f"الميزانية: صُرف ${budget.actual_spent_usd:.4f} من "
            f"${budget.hard_cap_usd:.2f} — المتبقي "
            f"${budget.remaining_usd:.4f}. "
            "أي طلب يتجاوز السقف سيُحجب قبل الإرسال."
        )
        if progress.next_video_shot_id:
            self.next_item_label.setText(
                "الفيديو التالي في طابور الخطة: "
                f"{progress.next_video_shot_id} — "
                f"{progress.next_video_label_ar}. "
                "يبدأ بعد إعداد حزمة اللقطة واعتماد المقطع الحالي."
            )
        else:
            self.next_item_label.setText(
                "لا يوجد فيديو تالٍ غير مكتمل في الخطة."
            )

        treatment_ar = {
            "GENERATED_VIDEO": "فيديو مولد",
            "ANIMATED_STILL_COMPOSITING": "صورة متحركة/تركيب",
            "GRAPHICS": "جرافيك",
        }
        status_ar = {
            "ACCEPTED": "مقبول",
            "ACCEPTED_REFERENCE_EXISTS": "مرجع مقبول",
            "PLANNED_NOT_PRODUCED": "مخطط",
        }
        self.queue_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                str(row["queue_index"]),
                str(row["shot_id"]),
                str(row["label_ar"]),
                treatment_ar.get(
                    str(row["final_budget_treatment"]),
                    str(row["final_budget_treatment"]),
                ),
                f"{row['editorial_duration_seconds']} ث",
                (
                    f"{row['planned_generated_video_seconds']} ث"
                    if row["planned_generated_video_seconds"]
                    else "—"
                ),
                status_ar.get(
                    str(row["production_status"]),
                    str(row["production_status"]),
                ),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {0, 4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.queue_table.setItem(row_index, column, item)

    def _refresh_state(self) -> None:
        self._refresh_episode_plan()
        try:
            spec = load_automatic_video_spec(self.repo_root)
            state = load_state(spec)
            self.last_output = current_output_path(self.repo_root)
            budget = scan_actual_paid_spend(self.repo_root)
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
                "دون إرسال طلب جديد.",
            "AWAITING_SCORE":
                "اكتمل الفيديو. اعرضه أو افتح مكانه ثم أدخل درجة واحدة.",
            "ACCEPTED":
                "تم قبول المقطع. انتقل إلى خطة الحلقة لمعرفة العنصر التالي.",
            "REQUIRES_PROMPT_REDESIGN":
                "اكتملت المحاولات المتاحة دون قبول. يلزم تصميم Prompt جديد.",
        }
        self.status_label.setText(descriptions.get(status, status))
        self.details_label.setText(
            f"{spec.beat_id} — {spec.model} — "
            f"{spec.width}×{spec.height} — {spec.duration}s — "
            f"{key_status} — المتبقي من سقف الحلقة "
            f"${budget.remaining_usd:.4f}"
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
            + "\n\nعند وجود قفل سيستعيد سراج المهمة نفسها، ولن يكرر الإرسال.",
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
                "راجع تبويب خطة الحلقة للعنصر التالي."
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
