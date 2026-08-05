from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QDir, QProcess, QThread, QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.application.autonomous_episode_orchestrator_v1 import (
    AutonomousOrchestratorError,
    approve_scope,
    current_scope_proposal,
    discuss_and_revise_scope,
    generate_next_episode_scope,
    load_orchestrator_state,
    provider_readiness,
)
from src.application.automatic_research_script_storyboard_runner_v1 import (
    EDITORIAL_MAX_BUDGET_USD,
    EditorialPipelineError,
    EditorialPipelineResult,
    load_editorial_runner_state,
    run_editorial_pipeline,
)
from src.application.graphics_storyboard_media_queue_v1 import (
    GraphicsMediaQueueError,
    GraphicsMediaQueueResult,
    integrate_graphics_and_build_media_queue,
)
from src.application.provider_credentials_v1 import (
    ProviderCredentialError,
    read_elevenlabs_api_key,
    read_openai_api_key,
    save_elevenlabs_api_key,
    save_openai_api_key,
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
from src.application.episode_cost_ledger_v1 import (
    current_episode_cost_breakdown,
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

PRODUCTION_CONSOLE_RELEASE = "AUTOMATIC_RESEARCH_SCRIPT_STORYBOARD_RUNNER_V1"

# Historical source-contract compatibility markers retained:
# paidExecutionConfirmation
# executeBeat01Button
# recoverBeat01Button
# saveBeat01ReviewButton
# QMessageBox.warning


class ScopeGenerationThread(QThread):
    progress_changed = Signal(str, object)
    generation_succeeded = Signal(object)
    generation_failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        api_key: str,
        instruction: str,
        revision: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root
        self._api_key = api_key
        self.instruction = instruction
        self.revision = revision

    def run(self) -> None:
        def progress(message: str, value: int | None) -> None:
            self.progress_changed.emit(message, value)

        try:
            if self.revision:
                result = discuss_and_revise_scope(
                    self.repo_root,
                    self._api_key,
                    self.instruction,
                    progress=progress,
                )
            else:
                result = generate_next_episode_scope(
                    self.repo_root,
                    self._api_key,
                    instruction=self.instruction,
                    progress=progress,
                )
        except Exception as exc:
            self.generation_failed.emit(str(exc))
        else:
            self.generation_succeeded.emit(result)
        finally:
            self._api_key = ""


class EditorialPipelineThread(QThread):
    progress_changed = Signal(str, object)
    pipeline_succeeded = Signal(object)
    pipeline_failed = Signal(str)

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
            result = run_editorial_pipeline(
                self.repo_root,
                self._api_key,
                progress=progress,
            )
        except Exception as exc:
            self.pipeline_failed.emit(str(exc))
        else:
            self.pipeline_succeeded.emit(result)
        finally:
            self._api_key = ""


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
        self.scope_worker: ScopeGenerationThread | None = None
        self.editorial_worker: EditorialPipelineThread | None = None
        self.last_output: Path | None = None
        self.setObjectName("productionConsoleDialog")
        self.setWindowTitle("سراج — الإنتاج الذاتي للحلقات")
        self.resize(1180, 840)
        self.setMinimumSize(960, 700)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()
        self._refresh_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("الإنتاج الذاتي للحلقات")
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

        self.orchestrator_tab = QWidget()
        self.orchestrator_tab.setObjectName("autonomousOrchestratorTab")
        self.tabs.addTab(self.orchestrator_tab, "الإنتاج الذاتي")
        self._build_orchestrator_tab()

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

    def _build_orchestrator_tab(self) -> None:
        layout = QVBoxLayout(self.orchestrator_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.orchestrator_status_label = QLabel("")
        self.orchestrator_status_label.setObjectName("orchestratorStatusLabel")
        self.orchestrator_status_label.setWordWrap(True)
        layout.addWidget(self.orchestrator_status_label)

        self.provider_readiness_label = QLabel("")
        self.provider_readiness_label.setObjectName("providerReadinessLabel")
        self.provider_readiness_label.setWordWrap(True)
        layout.addWidget(self.provider_readiness_label)

        key_row = QHBoxLayout()
        self.configure_openai_button = QPushButton("إعداد مفتاح OpenAI / Luna")
        self.configure_openai_button.setObjectName("configureOpenAIKeyButton")
        self.configure_openai_button.clicked.connect(self._configure_openai_key)
        key_row.addWidget(self.configure_openai_button)
        self.configure_elevenlabs_button = QPushButton("إعداد مفتاح ElevenLabs")
        self.configure_elevenlabs_button.setObjectName("configureElevenLabsKeyButton")
        self.configure_elevenlabs_button.clicked.connect(
            self._configure_elevenlabs_key
        )
        key_row.addWidget(self.configure_elevenlabs_button)
        layout.addLayout(key_row)

        instruction_label = QLabel("تعليمات اختيار الحلقة — اختيارية")
        instruction_label.setObjectName("sectionTitle")
        layout.addWidget(instruction_label)
        self.next_episode_instruction = QPlainTextEdit()
        self.next_episode_instruction.setObjectName("nextEpisodeInstructionInput")
        self.next_episode_instruction.setPlaceholderText(
            "مثال: اجعل الحلقة متصلة مباشرة بنهاية حلقة آدم، ولا تتجاوز 8 أحداث."
        )
        self.next_episode_instruction.setMaximumHeight(78)
        layout.addWidget(self.next_episode_instruction)

        self.produce_next_episode_button = QPushButton("إنتاج الحلقة التالية")
        self.produce_next_episode_button.setObjectName("produceNextEpisodeButton")
        self.produce_next_episode_button.setMinimumHeight(46)
        self.produce_next_episode_button.clicked.connect(
            self._produce_next_episode
        )
        layout.addWidget(self.produce_next_episode_button)

        self.scope_progress = QProgressBar()
        self.scope_progress.setObjectName("scopeGenerationProgress")
        self.scope_progress.setRange(0, 100)
        self.scope_progress.setValue(0)
        layout.addWidget(self.scope_progress)
        self.scope_progress_label = QLabel("جاهز.")
        self.scope_progress_label.setObjectName("scopeGenerationProgressLabel")
        self.scope_progress_label.setWordWrap(True)
        layout.addWidget(self.scope_progress_label)

        proposal_label = QLabel("مقترح الموضوع والأحداث")
        proposal_label.setObjectName("sectionTitle")
        layout.addWidget(proposal_label)
        self.scope_proposal_view = QPlainTextEdit()
        self.scope_proposal_view.setObjectName("scopeProposalView")
        self.scope_proposal_view.setReadOnly(True)
        self.scope_proposal_view.setMaximumHeight(145)
        layout.addWidget(self.scope_proposal_view)

        self.scope_events_table = QTableWidget()
        self.scope_events_table.setObjectName("scopeEventsTable")
        self.scope_events_table.setColumnCount(5)
        self.scope_events_table.setHorizontalHeaderLabels(
            ["#", "الحدث", "الموقف الدليلي", "الثقة", "المراجع"]
        )
        self.scope_events_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.scope_events_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.scope_events_table.setMaximumHeight(185)
        scope_header = self.scope_events_table.horizontalHeader()
        scope_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        scope_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        scope_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        scope_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        scope_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.scope_events_table)

        discussion_row = QHBoxLayout()
        self.scope_discussion_input = QPlainTextEdit()
        self.scope_discussion_input.setObjectName("scopeDiscussionInput")
        self.scope_discussion_input.setPlaceholderText(
            "ناقش المقترح مع Luna: احذف حدثًا، أضف حدثًا، غيّر الموضوع أو اطلب مصادر أقوى."
        )
        self.scope_discussion_input.setMaximumHeight(72)
        discussion_row.addWidget(self.scope_discussion_input, 3)
        self.send_scope_discussion_button = QPushButton("إرسال إلى Luna")
        self.send_scope_discussion_button.setObjectName(
            "sendScopeDiscussionButton"
        )
        self.send_scope_discussion_button.clicked.connect(
            self._send_scope_discussion
        )
        discussion_row.addWidget(self.send_scope_discussion_button, 1)
        layout.addLayout(discussion_row)

        self.approve_scope_button = QPushButton(
            "اعتماد الموضوع والأحداث وبدء البحث والنص والستوريبورد"
        )
        self.approve_scope_button.setObjectName("approveEpisodeScopeButton")
        self.approve_scope_button.setMinimumHeight(44)
        self.approve_scope_button.clicked.connect(self._approve_episode_scope)
        layout.addWidget(self.approve_scope_button)


        authorization_hint = QLabel(
            "اعتماد النطاق يفوض تلقائيًا ثلاث مراحل Luna بحد تحريري "
            f"أقصى ${EDITORIAL_MAX_BUDGET_USD:.2f} ضمن سقف الحلقة 40$. "
            "لا توجد إعادة مدفوعة خفية."
        )
        authorization_hint.setObjectName("muted")
        authorization_hint.setWordWrap(True)
        layout.addWidget(authorization_hint)

        self.editorial_pipeline_box = QGroupBox(
            "البحث والنص والستوريبورد الآلي"
        )
        self.editorial_pipeline_box.setObjectName(
            "editorialPipelineBox"
        )
        editorial_layout = QVBoxLayout(
            self.editorial_pipeline_box
        )
        editorial_layout.setContentsMargins(10, 10, 10, 10)
        editorial_layout.setSpacing(6)

        self.editorial_status_label = QLabel(
            "بانتظار اعتماد موضوع الحلقة وأحداثها."
        )
        self.editorial_status_label.setObjectName(
            "editorialPipelineStatusLabel"
        )
        self.editorial_status_label.setWordWrap(True)
        editorial_layout.addWidget(
            self.editorial_status_label
        )

        self.editorial_progress = QProgressBar()
        self.editorial_progress.setObjectName(
            "editorialPipelineProgress"
        )
        self.editorial_progress.setRange(0, 100)
        self.editorial_progress.setValue(0)
        editorial_layout.addWidget(self.editorial_progress)

        editorial_actions = QHBoxLayout()
        self.resume_editorial_button = QPushButton(
            "استئناف البحث والنص والستوريبورد"
        )
        self.resume_editorial_button.setObjectName(
            "resumeEditorialPipelineButton"
        )
        self.resume_editorial_button.clicked.connect(
            self._start_editorial_pipeline
        )
        editorial_actions.addWidget(
            self.resume_editorial_button
        )

        self.open_editorial_artifacts_button = QPushButton(
            "فتح مجلد الحلقة"
        )
        self.open_editorial_artifacts_button.setObjectName(
            "openEditorialArtifactsButton"
        )
        self.open_editorial_artifacts_button.clicked.connect(
            self._open_editorial_artifacts
        )
        editorial_actions.addWidget(
            self.open_editorial_artifacts_button
        )
        self.build_media_queue_button = QPushButton(
            "بناء/استئناف الجرافيك وطابور الوسائط"
        )
        self.build_media_queue_button.setObjectName(
            "buildMediaQueueButton"
        )
        self.build_media_queue_button.clicked.connect(
            self._build_media_queue
        )
        editorial_actions.addWidget(
            self.build_media_queue_button
        )
        editorial_layout.addLayout(editorial_actions)
        layout.addWidget(self.editorial_pipeline_box)

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

        self.episode_cost_box = QGroupBox("تكلفة الحلقة الحالية")
        self.episode_cost_box.setObjectName("episodeCostBreakdownBox")
        cost_layout = QVBoxLayout(self.episode_cost_box)
        cost_layout.setContentsMargins(10, 10, 10, 10)
        cost_layout.setSpacing(6)

        self.episode_cost_total_label = QLabel("")
        self.episode_cost_total_label.setObjectName("episodeCostTotalLabel")
        self.episode_cost_total_label.setWordWrap(True)
        cost_layout.addWidget(self.episode_cost_total_label)

        self.episode_cost_details_table = QTableWidget()
        self.episode_cost_details_table.setObjectName(
            "episodeCostDetailsTable"
        )
        self.episode_cost_details_table.setColumnCount(4)
        self.episode_cost_details_table.setHorizontalHeaderLabels(
            ["البند", "فعلي", "تقديري", "العمليات"]
        )
        self.episode_cost_details_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.episode_cost_details_table.setSelectionMode(
            QTableWidget.SelectionMode.NoSelection
        )
        self.episode_cost_details_table.setAlternatingRowColors(True)
        self.episode_cost_details_table.setMaximumHeight(190)
        cost_header = self.episode_cost_details_table.horizontalHeader()
        cost_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            cost_header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        cost_layout.addWidget(self.episode_cost_details_table)
        layout.addWidget(self.episode_cost_box)

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

    def _stored_openai_key(self) -> str | None:
        try:
            return read_openai_api_key()
        except ProviderCredentialError as exc:
            self.scope_progress_label.setText(str(exc))
            return None

    def _stored_elevenlabs_key(self) -> str | None:
        try:
            return read_elevenlabs_api_key()
        except ProviderCredentialError as exc:
            self.scope_progress_label.setText(str(exc))
            return None

    def _configure_openai_key(self) -> None:
        value, accepted = QInputDialog.getText(
            self,
            "إعداد مفتاح OpenAI",
            "ألصق OpenAI API Key الخاص بـGPT-5.6 Luna. سيُحفظ في Windows Credential Manager فقط:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return
        try:
            save_openai_api_key(value)
        except ProviderCredentialError as exc:
            QMessageBox.critical(self, "تعذر حفظ المفتاح", str(exc))
            return
        QMessageBox.information(self, "تم حفظ المفتاح", "تم حفظ مفتاح OpenAI بأمان.")
        self._refresh_state()

    def _configure_elevenlabs_key(self) -> None:
        value, accepted = QInputDialog.getText(
            self,
            "إعداد مفتاح ElevenLabs",
            "ألصق ElevenLabs API Key. سيُحفظ في Windows Credential Manager ويظل جاهزًا حتى شحن الرصيد:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return
        try:
            save_elevenlabs_api_key(value)
        except ProviderCredentialError as exc:
            QMessageBox.critical(self, "تعذر حفظ المفتاح", str(exc))
            return
        QMessageBox.information(self, "تم حفظ المفتاح", "تم حفظ مفتاح ElevenLabs بأمان.")
        self._refresh_state()

    def _ensure_openai_key(self) -> str | None:
        key = self._stored_openai_key()
        if key:
            return key
        self._configure_openai_key()
        return self._stored_openai_key()

    def _start_scope_worker(self, instruction: str, revision: bool) -> None:
        key = self._ensure_openai_key()
        if not key:
            return
        self.scope_worker = ScopeGenerationThread(
            self.repo_root,
            key,
            instruction,
            revision,
            self,
        )
        self.scope_worker.progress_changed.connect(self._on_scope_progress)
        self.scope_worker.generation_succeeded.connect(self._on_scope_success)
        self.scope_worker.generation_failed.connect(self._on_scope_failure)
        self.scope_worker.finished.connect(self._on_scope_finished)
        self.scope_progress.setRange(0, 0)
        self.scope_progress_label.setText("بدء بحث Luna…")
        self.scope_worker.start()
        self._refresh_state()

    def _produce_next_episode(self) -> None:
        instruction = self.next_episode_instruction.toPlainText().strip()
        self._start_scope_worker(instruction, revision=False)

    def _send_scope_discussion(self) -> None:
        message = self.scope_discussion_input.toPlainText().strip()
        if not message:
            QMessageBox.information(self, "رسالة مطلوبة", "اكتب التعديل المطلوب أولًا.")
            return
        self._start_scope_worker(message, revision=True)

    def _on_scope_progress(self, message: str, value: object) -> None:
        self.scope_progress_label.setText(message)
        if isinstance(value, int):
            self.scope_progress.setRange(0, 100)
            self.scope_progress.setValue(value)
        else:
            self.scope_progress.setRange(0, 0)

    def _on_scope_success(self, result: object) -> None:
        self.scope_progress.setRange(0, 100)
        self.scope_progress.setValue(100)
        self.scope_progress_label.setText(
            "اكتمل المقترح. ناقشه أو اعتمد الموضوع والأحداث."
        )
        self.scope_discussion_input.clear()
        self._refresh_state()

    def _on_scope_failure(self, error: str) -> None:
        self.scope_progress.setRange(0, 100)
        self.scope_progress.setValue(0)
        self.scope_progress_label.setText("توقفت العملية: " + error)
        QMessageBox.critical(self, "تعذر إنشاء مقترح الحلقة", error)
        self._refresh_state()

    def _on_scope_finished(self) -> None:
        if self.scope_worker is not None:
            self.scope_worker.deleteLater()
        self.scope_worker = None
        self._refresh_state()

    def _start_editorial_pipeline(self) -> None:
        if (
            self.editorial_worker is not None
            and self.editorial_worker.isRunning()
        ):
            return
        key = self._ensure_openai_key()
        if not key:
            return
        self.editorial_worker = EditorialPipelineThread(
            self.repo_root,
            key,
            self,
        )
        self.editorial_worker.progress_changed.connect(
            self._on_editorial_progress
        )
        self.editorial_worker.pipeline_succeeded.connect(
            self._on_editorial_success
        )
        self.editorial_worker.pipeline_failed.connect(
            self._on_editorial_failure
        )
        self.editorial_worker.finished.connect(
            self._on_editorial_finished
        )
        self.editorial_progress.setRange(0, 100)
        self.editorial_progress.setValue(0)
        self.editorial_status_label.setText(
            "بدء السلسلة التحريرية الآلية…"
        )
        self.editorial_worker.start()
        self._refresh_state()

    def _on_editorial_progress(
        self,
        message: str,
        value: object,
    ) -> None:
        self.editorial_status_label.setText(message)
        if isinstance(value, int):
            self.editorial_progress.setRange(0, 100)
            self.editorial_progress.setValue(value)
        else:
            self.editorial_progress.setRange(0, 0)

    def _on_editorial_success(self, result: object) -> None:
        if not isinstance(result, EditorialPipelineResult):
            self._on_editorial_failure(
                "INVALID_EDITORIAL_PIPELINE_RESULT"
            )
            return
        self.editorial_progress.setRange(0, 100)
        self.editorial_progress.setValue(100)
        queue_result = self._build_media_queue(
            show_success_dialog=False
        )
        if queue_result is None:
            return
        self.editorial_status_label.setText(
            "اكتمل البحث والنص والستوريبورد، وتم بناء "
            "مواصفات الجرافيك وطابور الوسائط."
        )
        QMessageBox.information(
            self,
            "اكتملت السلسلة التحريرية وطابور الوسائط",
            "الحلقة: "
            + result.episode_id
            + "\nاكتملت حزمة الأدلة والنص و70 لقطة."
            + "\nالصور: "
            + str(queue_result.image_count)
            + " | الفيديو: "
            + str(queue_result.video_count)
            + " | الجرافيك المحلي: "
            + str(queue_result.graphics_count)
            + "\nمقاطع TTS: "
            + str(queue_result.tts_segment_count)
            + " — الأصوات الأربعة المختارة موزعة حسب السيناريو."
            + "\nالاحتياطي الوقائي الأقصى: $"
            + f"{queue_result.reserved_max_usd:.2f}"
            + "\nتكلفة النص التقديرية المسجلة: "
            + f"${result.estimated_text_cost_usd:.4f}"
            + "\nطلبات بحث الويب المسجلة: "
            + str(result.web_search_calls),
        )
        self._refresh_state()

    def _build_media_queue(
        self,
        checked: bool = False,
        *,
        show_success_dialog: bool = True,
    ) -> GraphicsMediaQueueResult | None:
        del checked
        try:
            result = integrate_graphics_and_build_media_queue(
                self.repo_root
            )
        except GraphicsMediaQueueError as exc:
            self.editorial_status_label.setText(
                "توقف بناء مواصفات الجرافيك وطابور الوسائط: "
                + str(exc)
            )
            QMessageBox.critical(
                self,
                "تعذر بناء طابور الوسائط",
                str(exc)
                + "\n\nلم يُرسل أي طلب مدفوع. "
                "استخدم زر البناء/الاستئناف بعد معالجة السبب.",
            )
            self._refresh_state()
            return None
        self.editorial_status_label.setText(
            "طابور الوسائط جاهز: "
            f"{result.image_count} صورة، "
            f"{result.video_count} فيديو، "
            f"{result.graphics_count} جرافيك محلي. "
            "الأصوات الأربعة المختارة موزعة تلقائيًا حسب السيناريو."
        )
        if show_success_dialog:
            QMessageBox.information(
                self,
                "طابور الوسائط جاهز",
                "تم بناء مواصفات الجرافيك والطوابير محليًا "
                "دون طلبات مدفوعة."
                + "\nالاحتياطي الوقائي الأقصى: $"
                + f"{result.reserved_max_usd:.2f}"
                + "\nلا توجد بوابة اختيار صوت جديدة؛ الطاقم مثبت.",
            )
        self._refresh_state()
        return result

    def _on_editorial_failure(self, error: str) -> None:
        self.editorial_progress.setRange(0, 100)
        self.editorial_status_label.setText(
            "توقفت السلسلة التحريرية: " + error
        )
        QMessageBox.critical(
            self,
            "توقف البحث أو النص أو الستوريبورد",
            error
            + "\n\nلا يعيد سراج طلبًا مدفوعًا تلقائيًا. "
            "استخدم زر الاستئناف بعد معالجة السبب.",
        )
        self._refresh_state()

    def _on_editorial_finished(self) -> None:
        if self.editorial_worker is not None:
            self.editorial_worker.deleteLater()
        self.editorial_worker = None
        self._refresh_state()

    def _open_editorial_artifacts(self) -> None:
        try:
            state = load_orchestrator_state(self.repo_root)
        except Exception:
            return
        episode_id = state.get("current_episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            return
        episode_root = (
            self.repo_root / "projects" / episode_id
        )
        if episode_root.is_dir():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(episode_root))
            )

    def _approve_episode_scope(self) -> None:
        try:
            state = approve_scope(self.repo_root)
        except AutonomousOrchestratorError as exc:
            QMessageBox.critical(
                self,
                "تعذر اعتماد النطاق",
                str(exc),
            )
            return
        self.scope_progress_label.setText(
            "تم اعتماد "
            + str(state.get("current_episode_id"))
            + "؛ يبدأ الآن البحث والنص والستوريبورد تلقائيًا."
        )
        self._refresh_state()
        self._start_editorial_pipeline()

    def _refresh_orchestrator_state(self) -> None:
        try:
            state = load_orchestrator_state(self.repo_root)
            editorial_state = load_editorial_runner_state(
                self.repo_root
            )
            proposal = current_scope_proposal(self.repo_root)
            readiness = provider_readiness(
                self.repo_root,
                openai_key_present=bool(self._stored_openai_key()),
                elevenlabs_key_present=bool(self._stored_elevenlabs_key()),
                runware_key_present=bool(self._stored_api_key()),
            )
        except Exception as exc:
            self.orchestrator_status_label.setText("تعذر قراءة حالة المنسق: " + str(exc))
            return

        status = str(state.get("status", "UNKNOWN"))
        status_text = {
            "IDLE_READY_FOR_NEXT_EPISODE": "جاهز. اضغط «إنتاج الحلقة التالية» ليختار Luna الموضوع والأحداث.",
            "GENERATING_SCOPE_WITH_LUNA": "Luna يبحث الآن ويُنشئ مقترح الموضوع والأحداث.",
            "AWAITING_HUMAN_SCOPE_REVIEW": "بوابة المراجعة البشرية مفتوحة: ناقش المقترح ثم اعتمده.",
            "SCOPE_PROVIDER_ERROR": "توقف مزود Luna. أصلح المفتاح أو الرصيد ثم أعد المحاولة.",
            "SCOPE_APPROVED_AUTOMATIC_PIPELINE_QUEUED": "تم اعتماد النطاق. البحث والنص والستوريبورد جاهزة للبدء الآلي.",
            "RUNNING_EVIDENCE_RESEARCH": "Luna يجمع الأدلة والمصادر المعتمدة.",
            "RUNNING_SCRIPT_WRITING": "Luna يكتب النص من حزمة الأدلة.",
            "RUNNING_STORYBOARD_AND_MEDIA_PLANNING": "Luna يبني الستوريبورد وخطة الوسائط.",
            "EDITORIAL_PIPELINE_FAILED": "توقفت السلسلة التحريرية ويمكن استئنافها بعد معالجة السبب.",
            "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED": "اكتمل البحث والنص والستوريبورد؛ مواصفات الجرافيك وطابور الوسائط هي المرحلة التالية.",
            "GRAPHICS_MEDIA_QUEUE_FAILED": "توقف بناء الجرافيك أو طابور الوسائط ويمكن استئنافه دون طلب مدفوع.",
            "MEDIA_QUEUE_READY": "مواصفات الجرافيك وطابور الوسائط جاهزة؛ طاقم ElevenLabs مثبت والتنفيذ المكتبي هو التالي.",
        }.get(status, status)
        self.orchestrator_status_label.setText(status_text)
        self.provider_readiness_label.setText(
            "المزودون: Luna=" + readiness["openai_luna"]
            + " | Runware=" + readiness["runware"]
            + " | ElevenLabs=" + readiness["elevenlabs"]
            + " | المونتاج=" + readiness["montage"]
            + " | المؤثرات=" + readiness["sfx"]
        )


        editorial_status = str(
            editorial_state.get("status", "NO_APPROVED_EPISODE")
        )
        completed_editorial = editorial_state.get(
            "completed_stages",
            [],
        )
        completed_count = (
            len(completed_editorial)
            if isinstance(completed_editorial, list)
            else 0
        )
        editorial_messages = {
            "NO_APPROVED_EPISODE": (
                "بانتظار اعتماد موضوع الحلقة وأحداثها."
            ),
            "READY_AFTER_SCOPE_APPROVAL": (
                "النطاق معتمد والسلسلة التحريرية جاهزة."
            ),
            "RUNNING_EVIDENCE_RESEARCH": (
                "مرحلة 1/3: بناء حزمة الأدلة."
            ),
            "RUNNING_SCRIPT_WRITING": (
                "مرحلة 2/3: كتابة النص الموثق."
            ),
            "RUNNING_STORYBOARD_AND_MEDIA_PLANNING": (
                "مرحلة 3/3: بناء 70 لقطة وخطة الوسائط."
            ),
            "EDITORIAL_PIPELINE_FAILED": (
                "توقفت العملية: "
                + str(editorial_state.get("last_error", ""))
            ),
            "EDITORIAL_PIPELINE_COMPLETE": (
                "اكتملت حزمة الأدلة والنص والستوريبورد."
            ),
        }
        self.editorial_status_label.setText(
            editorial_messages.get(
                editorial_status,
                editorial_status,
            )
        )
        self.editorial_progress.setRange(0, 100)
        self.editorial_progress.setValue(
            100
            if editorial_status == "EDITORIAL_PIPELINE_COMPLETE"
            else min(99, completed_count * 33)
        )

        if proposal:
            self.scope_proposal_view.setPlainText(
                "الموضوع: " + str(proposal.get("topic_title_ar", ""))
                + "\nالعنوان: " + str(proposal.get("working_title_ar", ""))
                + "\nالسؤال المركزي: " + str(proposal.get("central_question_ar", ""))
                + "\nالملخص: " + str(proposal.get("episode_summary_ar", ""))
                + "\nالمدة المتوقعة: "
                + str(proposal.get("estimated_duration_minutes", ""))
                + " دقيقة"
            )
            events = proposal.get("events")
            if not isinstance(events, list):
                events = []
            self.scope_events_table.setRowCount(len(events))
            for row_index, event in enumerate(events):
                refs = event.get("source_refs") if isinstance(event, dict) else []
                values = [
                    str(event.get("chronology_order", row_index + 1)),
                    str(event.get("title_ar", "")),
                    str(event.get("evidence_posture", "")),
                    str(event.get("confidence", "")),
                    str(len(refs) if isinstance(refs, list) else 0),
                ]
                for column, value in enumerate(values):
                    self.scope_events_table.setItem(
                        row_index,
                        column,
                        QTableWidgetItem(value),
                    )
        else:
            self.scope_proposal_view.setPlainText("لا يوجد مقترح بعد.")
            self.scope_events_table.setRowCount(0)

        running = (
            (
                self.scope_worker is not None
                and self.scope_worker.isRunning()
            )
            or (
                self.editorial_worker is not None
                and self.editorial_worker.isRunning()
            )
        )
        self.produce_next_episode_button.setEnabled(
            not running
            and status in {
                "IDLE_READY_FOR_NEXT_EPISODE",
                "SCOPE_PROVIDER_ERROR",
            }
        )
        review_open = status == "AWAITING_HUMAN_SCOPE_REVIEW"
        self.send_scope_discussion_button.setEnabled(not running and review_open)
        self.scope_discussion_input.setEnabled(not running and review_open)
        self.approve_scope_button.setEnabled(not running and review_open)
        self.resume_editorial_button.setEnabled(
            not running
            and editorial_status in {
                "READY_AFTER_SCOPE_APPROVAL",
                "EDITORIAL_PIPELINE_FAILED",
            }
        )
        self.open_editorial_artifacts_button.setEnabled(
            isinstance(state.get("current_episode_id"), str)
            and bool(state.get("current_episode_id"))
        )
        self.build_media_queue_button.setEnabled(
            not running
            and status in {
                "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED",
                "GRAPHICS_MEDIA_QUEUE_FAILED",
                "MEDIA_QUEUE_READY",
            }
        )
        self.configure_openai_button.setEnabled(not running)
        self.configure_elevenlabs_button.setEnabled(not running)

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
            costs = current_episode_cost_breakdown(self.repo_root)
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


        pending_scope = (
            f" — نطاق الحلقة التالية قبل الاعتماد: "
            f"${costs.pending_scope_estimated_usd:.4f} تقديري"
            if costs.pending_scope_estimated_usd > 0
            else ""
        )
        self.episode_cost_total_label.setText(
            f"الحلقة: {costs.episode_id} — الإجمالي المسجل "
            f"${costs.recorded_total_usd:.4f} "
            f"(فعلي ${costs.actual_cost_usd:.4f} + "
            f"تقديري ${costs.estimated_cost_usd:.4f}) — "
            f"المتبقي ${costs.remaining_usd:.4f} من "
            f"${costs.hard_cap_usd:.2f} — "
            f"العمليات المدفوعة: {costs.paid_operations}"
            f"{pending_scope}"
        )
        self.episode_cost_details_table.setRowCount(len(costs.categories))
        for row_index, category in enumerate(costs.categories):
            values = (
                category.label_ar,
                f"${category.actual_cost_usd:.4f}",
                f"${category.estimated_cost_usd:.4f}",
                str(category.paid_operations),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {1, 2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.episode_cost_details_table.setItem(
                    row_index,
                    column,
                    item,
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
        self._refresh_orchestrator_state()
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
        if self.scope_worker is not None and self.scope_worker.isRunning():
            QMessageBox.information(
                self,
                "البحث مستمر",
                "اترك النافذة مفتوحة حتى ينتهي Luna من المقترح بأمان.",
            )
            return
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self,
                "التوليد مستمر",
                "اترك النافذة مفتوحة حتى تنتهي العملية بأمان.",
            )
            return
        super().reject()
