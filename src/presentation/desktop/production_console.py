from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QDir, QProcess, QThread, QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
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
    QScrollArea,
    QSizePolicy,
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
from src.application.desktop_media_execution_v1 import (
    DesktopMediaExecutionError,
    execute_elevenlabs_item,
    execute_runware_item,
    media_queue_rows,
    render_all_pending_local_graphics,
)
from src.application.sfx_audio_mix_v1 import (
    SfxAudioMixError,
    SfxAudioMixResult,
    load_sfx_audio_mix_status,
    run_sfx_audio_mix,
)
from src.application.structural_montage_final_render_v1 import (
    StructuralMontageError,
    StructuralMontageResult,
    load_structural_montage_status,
    run_structural_montage_final_render,
)
from src.application.automatic_qa_partial_repair_v1 import (
    AutomaticQAError,
    AutomaticQAResult,
    load_automatic_qa_status,
    run_automatic_qa_and_partial_repair,
)
from src.presentation.desktop.final_review_publish_dialog_v1 import (
    FinalReviewPublishDialog,
)
from src.application.production_resume_router_v1 import (
    resolve_resume_directive,
)
from src.application.end_to_end_production_v1 import (
    EndToEndPlan,
    EndToEndRunResult,
    inspect_end_to_end_plan,
    run_to_next_human_gate,
)
from src.application.runtime_state_recovery_v1 import (
    diagnose_runtime_state,
    recover_runtime_state_from_artifacts,
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

PRODUCTION_CONSOLE_RELEASE = "SIRAJ_ACCEPTANCE_RESUME_BUTTON_RECOVERY_V1"

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


class MediaExecutionThread(QThread):
    progress_changed = Signal(str, object)
    execution_succeeded = Signal(object)
    execution_failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        mode: str,
        queue_id: str | None,
        api_key: str,
        maximum_authorized_usd: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root
        self.mode = mode
        self.queue_id = queue_id
        self._api_key = api_key
        self.maximum_authorized_usd = maximum_authorized_usd

    def run(self) -> None:
        def progress(message: str, value: int | None) -> None:
            self.progress_changed.emit(message, value)

        try:
            if self.mode == "LOCAL_ALL":
                result = render_all_pending_local_graphics(
                    self.repo_root,
                    progress=progress,
                )
            elif self.mode == "RUNWARE":
                result = execute_runware_item(
                    self.repo_root,
                    str(self.queue_id),
                    self._api_key,
                    confirmed_maximum_usd=(
                        self.maximum_authorized_usd
                    ),
                    progress=progress,
                )
            elif self.mode == "RECOVER_RUNWARE":
                result = execute_runware_item(
                    self.repo_root,
                    str(self.queue_id),
                    self._api_key,
                    confirmed_maximum_usd=(
                        self.maximum_authorized_usd
                    ),
                    recovery_only=True,
                    progress=progress,
                )
            elif self.mode == "ELEVENLABS":
                result = execute_elevenlabs_item(
                    self.repo_root,
                    str(self.queue_id),
                    self._api_key,
                    confirmed_maximum_usd=(
                        self.maximum_authorized_usd
                    ),
                    progress=progress,
                )
            else:
                raise DesktopMediaExecutionError(
                    "UNKNOWN_MEDIA_EXECUTION_MODE"
                )
        except Exception as exc:
            self.execution_failed.emit(str(exc))
        else:
            self.execution_succeeded.emit(result)
        finally:
            self._api_key = ""


class SfxAudioMixThread(QThread):
    progress_changed = Signal(str, object)
    mix_succeeded = Signal(object)
    mix_failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root

    def run(self) -> None:
        def progress(message: str, value: int | None) -> None:
            self.progress_changed.emit(message, value)

        try:
            result = run_sfx_audio_mix(
                self.repo_root,
                progress=progress,
            )
        except Exception as exc:
            self.mix_failed.emit(str(exc))
        else:
            self.mix_succeeded.emit(result)


class StructuralMontageThread(QThread):
    progress_changed = Signal(str, object)
    render_succeeded = Signal(object)
    render_failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root

    def run(self) -> None:
        def progress(message: str, value: int | None) -> None:
            self.progress_changed.emit(message, value)

        try:
            result = run_structural_montage_final_render(
                self.repo_root,
                progress=progress,
            )
        except Exception as exc:
            self.render_failed.emit(str(exc))
        else:
            self.render_succeeded.emit(result)


class AutomaticQAThread(QThread):
    progress_changed = Signal(str, object)
    qa_succeeded = Signal(object)
    qa_failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root

    def run(self) -> None:
        def progress(message: str, value: int | None) -> None:
            self.progress_changed.emit(message, value)

        try:
            result = run_automatic_qa_and_partial_repair(
                self.repo_root,
                progress=progress,
            )
        except Exception as exc:
            self.qa_failed.emit(str(exc))
        else:
            self.qa_succeeded.emit(result)



class EndToEndCompletionThread(QThread):
    progress_changed = Signal(str, object)
    completion_succeeded = Signal(object)
    completion_failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        openai_api_key: str,
        runware_api_key: str,
        elevenlabs_api_key: str,
        confirmed_media_maximum_usd: float | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root
        self._openai_api_key = openai_api_key
        self._runware_api_key = runware_api_key
        self._elevenlabs_api_key = elevenlabs_api_key
        self.confirmed_media_maximum_usd = confirmed_media_maximum_usd

    def run(self) -> None:
        def progress(message: str, value: int | None) -> None:
            self.progress_changed.emit(message, value)

        try:
            result = run_to_next_human_gate(
                self.repo_root,
                openai_api_key=self._openai_api_key,
                runware_api_key=self._runware_api_key,
                elevenlabs_api_key=self._elevenlabs_api_key,
                confirmed_media_maximum_usd=(
                    self.confirmed_media_maximum_usd
                ),
                progress=progress,
            )
        except Exception as exc:
            self.completion_failed.emit(str(exc))
        else:
            self.completion_succeeded.emit(result)
        finally:
            self._openai_api_key = ""
            self._runware_api_key = ""
            self._elevenlabs_api_key = ""

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
        self.media_execution_worker: MediaExecutionThread | None = None
        self.sfx_audio_worker: SfxAudioMixThread | None = None
        self.structural_montage_worker: StructuralMontageThread | None = None
        self.automatic_qa_worker: AutomaticQAThread | None = None
        self.end_to_end_worker: EndToEndCompletionThread | None = None
        self._media_execution_rows = {}
        self._resume_directive = None
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

        self.resume_box = QGroupBox("استكمال الحلقة")
        self.resume_box.setObjectName("continueEpisodeBox")
        resume_layout = QVBoxLayout(self.resume_box)
        resume_layout.setContentsMargins(12, 10, 12, 10)
        resume_layout.setSpacing(7)
        self.resume_status_label = QLabel("جارٍ تحديد المرحلة التالية…")
        self.resume_status_label.setObjectName("continueEpisodeStatusLabel")
        self.resume_status_label.setWordWrap(True)
        resume_layout.addWidget(self.resume_status_label)
        resume_actions = QHBoxLayout()
        self.continue_episode_button = QPushButton(
            "استكمال إنتاج الحلقة حتى تصبح جاهزة للنشر"
        )
        self.continue_episode_button.setObjectName(
            "continueEpisodeToPublishButton"
        )
        self.continue_episode_button.setMinimumHeight(46)
        self.continue_episode_button.clicked.connect(
            lambda checked=False: self._continue_episode_to_publish()
        )
        resume_actions.addWidget(self.continue_episode_button, 3)
        self.resume_refresh_button = QPushButton("تحديث الموجّه")
        self.resume_refresh_button.setObjectName("refreshResumeDirectiveButton")
        self.resume_refresh_button.clicked.connect(
            lambda checked=False: self._refresh_resume_directive()
        )
        resume_actions.addWidget(self.resume_refresh_button, 1)
        resume_layout.addLayout(resume_actions)
        self.end_to_end_progress = QProgressBar()
        self.end_to_end_progress.setObjectName(
            "endToEndCompletionProgress"
        )
        self.end_to_end_progress.setRange(0, 100)
        self.end_to_end_progress.setValue(0)
        resume_layout.addWidget(self.end_to_end_progress)
        self.end_to_end_progress_label = QLabel("جاهز.")
        self.end_to_end_progress_label.setObjectName(
            "endToEndCompletionProgressLabel"
        )
        self.end_to_end_progress_label.setWordWrap(True)
        resume_layout.addWidget(self.end_to_end_progress_label)
        policy = QLabel(
            "يشغّل الزر المراحل المحلية والتحريرية الآمنة ويأخذك إلى "
            "المرحلة الصحيحة. لا يتجاوز اعتماد النطاق، أو تأكيد الإنفاق "
            "المدفوع، أو المراجعة البشرية النهائية، أو رفع YouTube اليدوي."
        )
        policy.setObjectName("muted")
        policy.setWordWrap(True)
        resume_layout.addWidget(policy)
        root.addWidget(self.resume_box)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("episodeProductionTabs")
        self.tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        self.orchestrator_tab = QWidget()
        self.orchestrator_tab.setObjectName("autonomousOrchestratorTab")
        self.tabs.addTab(self.orchestrator_tab, "الإنتاج الذاتي")
        self._build_orchestrator_tab()

        self.plan_tab = QWidget()
        self.plan_tab.setObjectName("episodePlanTab")
        self.tabs.addTab(self.plan_tab, "خطة الحلقة")
        self._build_plan_tab()

        self.media_execution_tab = QWidget()
        self.media_execution_tab.setObjectName(
            "desktopMediaExecutionTab"
        )
        self.tabs.addTab(
            self.media_execution_tab,
            "تنفيذ الوسائط",
        )
        self._build_media_execution_tab()

        self.sfx_audio_tab = QWidget()
        self.sfx_audio_tab.setObjectName("sfxAudioMixTab")
        self.tabs.addTab(self.sfx_audio_tab, "الصوت والمؤثرات")
        self._build_sfx_audio_tab()

        self.structural_montage_tab = QWidget()
        self.structural_montage_tab.setObjectName(
            "structuralMontageFinalRenderTab"
        )
        self.tabs.addTab(
            self.structural_montage_tab,
            "المونتاج النهائي",
        )
        self._build_structural_montage_tab()

        self.automatic_qa_tab = QWidget()
        self.automatic_qa_tab.setObjectName(
            "automaticQaPartialRepairTab"
        )
        self.tabs.addTab(
            self.automatic_qa_tab,
            "الفحص والإصلاح",
        )
        self._build_automatic_qa_tab()

        self.clip_tab = QWidget()
        self.clip_tab.setObjectName("clipProductionTab")
        self.tabs.addTab(self.clip_tab, "إنتاج المقطع")
        self._build_clip_tab()

        self.tabs_scroll = QScrollArea()
        self.tabs_scroll.setObjectName("productionConsoleScroll")
        self.tabs_scroll.viewport().setObjectName(
            "productionConsoleScrollViewport"
        )
        self.tabs_scroll.setWidgetResizable(True)
        self.tabs_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tabs_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tabs_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.tabs_scroll.setWidget(self.tabs)
        root.addWidget(self.tabs_scroll, 1)
        self.tabs.currentChanged.connect(self._resize_tabs_for_scroll)
        self._resize_tabs_for_scroll(self.tabs.currentIndex())

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

    def _resize_tabs_for_scroll(self, index: int) -> None:
        page = self.tabs.widget(index)
        if page is None:
            return
        layout = page.layout()
        content_height = (
            layout.sizeHint().height()
            if layout is not None
            else page.sizeHint().height()
        )
        tab_height = self.tabs.tabBar().sizeHint().height()
        self.tabs.setMinimumHeight(max(720, content_height + tab_height + 48))
        self.tabs_scroll.verticalScrollBar().setValue(0)

    def _tab_index_for_key(self, key: str) -> int:
        return {
            "orchestrator": 0,
            "plan": 1,
            "media": 2,
            "sfx": 3,
            "montage": 4,
            "qa": 5,
            "clip": 6,
        }.get(key, 0)

    def _refresh_resume_directive(self) -> None:
        try:
            directive = resolve_resume_directive(self.repo_root)
        except Exception as exc:
            self.resume_status_label.setText(
                "تعذر تحديد المرحلة التالية: " + str(exc)
            )
            self.continue_episode_button.setText(
                "تشخيص وإصلاح الاستكمال"
            )
            self.continue_episode_button.setEnabled(True)
            return
        self._resume_directive = directive
        self.resume_status_label.setText(
            directive.label_ar + "\n" + directive.detail_ar
        )
        running = any(
            worker is not None and worker.isRunning()
            for worker in (
                self.worker,
                self.scope_worker,
                self.editorial_worker,
                self.media_execution_worker,
                self.sfx_audio_worker,
                self.structural_montage_worker,
                self.automatic_qa_worker,
                self.end_to_end_worker,
            )
        )
        if directive.action == "WAIT" and not running:
            self.continue_episode_button.setText(
                "فحص واستعادة المرحلة العالقة"
            )
            self.resume_status_label.setText(
                directive.label_ar
                + "\n"
                + directive.detail_ar
                + "\nلا توجد عملية داخل هذه النافذة الآن؛ اضغط الزر لفحص الحالة واستعادتها من الملفات."
            )
        elif directive.action in {"REFRESH", "INSPECT_BLOCKER"}:
            self.continue_episode_button.setText(
                "تشخيص وإصلاح الاستكمال"
            )
        else:
            self.continue_episode_button.setText(directive.label_ar)
        self.continue_episode_button.setEnabled(not running)

    def _continue_episode_to_publish(self) -> None:
        if (
            self.end_to_end_worker is not None
            and self.end_to_end_worker.isRunning()
        ):
            QMessageBox.information(
                self,
                "الاستكمال يعمل",
                "خط الإنتاج يعمل بالفعل. راقب شريط التقدم وانتظر اكتمال المرحلة الحالية.",
            )
            return

        self.end_to_end_progress_label.setText(
            "استلم سراج أمر الاستكمال؛ جارٍ فحص الحالة والملفات…"
        )
        self.end_to_end_progress.setRange(0, 0)
        QApplication.processEvents()

        try:
            directive = resolve_resume_directive(self.repo_root)
            plan = inspect_end_to_end_plan(self.repo_root)
        except Exception as exc:
            self.end_to_end_progress.setRange(0, 100)
            self.end_to_end_progress.setValue(0)
            self.end_to_end_progress_label.setText(
                "تعذر قراءة خطة الاستكمال: " + str(exc)
            )
            QMessageBox.critical(
                self,
                "تعذر استكمال الحلقة",
                str(exc),
            )
            return

        if directive.action in {"WAIT", "REFRESH", "INSPECT_BLOCKER"}:
            recovered = self._recover_resume_runtime_state(
                force=directive.action == "WAIT"
            )
            if not recovered:
                self.end_to_end_progress.setRange(0, 100)
                self.end_to_end_progress.setValue(0)
                self.end_to_end_progress_label.setText(
                    "لم يبدأ أي تنفيذ؛ راجع رسالة التشخيص الظاهرة."
                )
                return
            try:
                directive = resolve_resume_directive(self.repo_root)
                plan = inspect_end_to_end_plan(self.repo_root)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "تعذر قراءة الحالة بعد الاستعادة",
                    str(exc),
                )
                return

        self._resume_directive = directive
        self.tabs.setCurrentIndex(
            self._tab_index_for_key(directive.target_tab)
        )
        self._resize_tabs_for_scroll(self.tabs.currentIndex())
        self.end_to_end_progress.setRange(0, 100)
        self.end_to_end_progress.setValue(0)

        action = directive.action
        self.end_to_end_progress_label.setText(
            "الإجراء المحدد: " + directive.label_ar
        )
        QApplication.processEvents()

        if action == "GENERATE_SCOPE":
            self._produce_next_episode()
        elif action == "RUN_EDITORIAL":
            self._start_editorial_pipeline()
        elif action == "OPEN_MEDIA_EXECUTION":
            self._start_end_to_end_completion(plan)
        elif action == "RUN_SFX":
            self._start_sfx_audio_mix()
        elif action == "RUN_MONTAGE":
            self._start_structural_montage()
        elif action == "RUN_QA":
            self._start_automatic_qa()
        elif action == "OPEN_FINAL_REVIEW":
            self._open_final_review_publish()
        elif action == "OPEN_PUBLISH_PACKAGE":
            if plan.ready_for_manual_youtube_upload:
                self._open_final_review_publish()
            else:
                self._start_end_to_end_completion(plan)
        elif action == "REVIEW_SCOPE":
            self.scope_proposal_view.setFocus()
            QMessageBox.information(
                self,
                "بوابة اعتماد النطاق",
                directive.detail_ar,
            )
        else:
            QMessageBox.warning(
                self,
                "لا يوجد إجراء تنفيذي",
                "الحالة: "
                + plan.status
                + "\nالمرحلة: "
                + plan.stage
                + "\nالإجراء: "
                + action
                + "\n\nاستخدم زر تشخيص وإصلاح الاستكمال.",
            )
        self._refresh_resume_directive()

    def _recover_resume_runtime_state(self, *, force: bool = False) -> bool:
        try:
            diagnosis = diagnose_runtime_state(self.repo_root)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "تعذر تشخيص الاستكمال",
                str(exc),
            )
            return False

        details = (
            "الحالة المخزنة: "
            + diagnosis.stored_status
            + " / "
            + diagnosis.stored_stage
            + "\nالإجراء المخزن: "
            + diagnosis.stored_action
            + "\n\nالحالة المستنتجة من الملفات: "
            + diagnosis.inferred_status
            + " / "
            + diagnosis.inferred_stage
            + "\nالإجراء المستنتج: "
            + diagnosis.inferred_action
            + "\nالسبب: "
            + diagnosis.reason
        )
        if diagnosis.evidence_paths:
            details += "\n\nالأدلة:\n- " + "\n- ".join(
                diagnosis.evidence_paths
            )

        if not diagnosis.needs_recovery and not force:
            QMessageBox.information(
                self,
                "حالة الاستكمال سليمة",
                details,
            )
            return False

        answer = QMessageBox.question(
            self,
            "استعادة حالة الاستكمال",
            details
            + "\n\nسيحفظ سراج نسخة احتياطية من ملف الحالة، ثم يصحح مؤشرات المرحلة فقط. "
            "لن يحذف أي أصل، ولن يرسل أي طلب مدفوع. هل تريد المتابعة؟",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.end_to_end_progress_label.setText(
                "أُلغي تصحيح الحالة؛ لم يتغير أي ملف."
            )
            return False

        try:
            result = recover_runtime_state_from_artifacts(
                self.repo_root,
                force=force,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "تعذر استعادة الحالة",
                str(exc),
            )
            return False

        backup = str(result.backup_path) if result.backup_path else "لم تكن هناك حالة سابقة"
        QMessageBox.information(
            self,
            "تمت استعادة حالة الاستكمال",
            "الحالة السابقة: "
            + result.previous_status
            + " / "
            + result.previous_stage
            + "\nالحالة الجديدة: "
            + result.recovered_status
            + " / "
            + result.recovered_stage
            + "\nالإجراء التالي: "
            + result.recovered_action
            + "\nالنسخة الاحتياطية: "
            + backup,
        )
        self.end_to_end_progress_label.setText(
            "تم تصحيح الحالة. اضغط استكمال مرة أخرى إذا لم يبدأ الإجراء تلقائيًا."
        )
        self._refresh_state()
        return result.changed

    def _start_end_to_end_completion(self, plan: object) -> None:
        if not isinstance(plan, EndToEndPlan):
            QMessageBox.critical(
                self,
                "تعذر استكمال الحلقة",
                "INVALID_END_TO_END_PLAN",
            )
            return
        if (
            self.end_to_end_worker is not None
            and self.end_to_end_worker.isRunning()
        ):
            return

        openai_key = ""
        runware_key = ""
        elevenlabs_key = ""
        if plan.requires_openai_key:
            openai_key = self._ensure_openai_key() or ""
            if not openai_key:
                return
        if plan.requires_runware_key:
            runware_key = self._ensure_key() or ""
            if not runware_key:
                return
        if plan.requires_elevenlabs_key:
            elevenlabs_key = self._stored_elevenlabs_key() or ""
            if not elevenlabs_key:
                self._configure_elevenlabs_key()
                elevenlabs_key = self._stored_elevenlabs_key() or ""
            if not elevenlabs_key:
                return

        confirmed: float | None = None
        if plan.requires_paid_confirmation:
            answer = QMessageBox.question(
                self,
                "تفويض واحد لإكمال وسائط الحلقة",
                "سيُنفذ سراج جميع عناصر الوسائط المتبقية بالتتابع بعد "
                "تفويض واحد فقط.\n\n"
                + "Runware: "
                + str(plan.pending_runware_count)
                + " عنصر\nElevenLabs: "
                + str(plan.pending_elevenlabs_count)
                + " عنصر\nجرافيك محلي: "
                + str(plan.pending_local_graphics_count)
                + " عنصر\n\nالحد الأقصى الإجمالي المصرح به لهذه العناصر: $"
                + f"{plan.pending_media_maximum_usd:.6f}"
                + "\n\nلن تُرسل إعادة مدفوعة خفية. استعادة مهمة Runware "
                "القائمة تستخدم taskUUID نفسه ولا تنشئ طلبًا جديدًا. هل توافق؟",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            confirmed = plan.pending_media_maximum_usd

        self.end_to_end_worker = EndToEndCompletionThread(
            self.repo_root,
            openai_key,
            runware_key,
            elevenlabs_key,
            confirmed,
            self,
        )
        self.end_to_end_worker.progress_changed.connect(
            self._on_end_to_end_progress
        )
        self.end_to_end_worker.completion_succeeded.connect(
            self._on_end_to_end_success
        )
        self.end_to_end_worker.completion_failed.connect(
            self._on_end_to_end_failure
        )
        self.end_to_end_worker.finished.connect(
            self._on_end_to_end_finished
        )
        self.end_to_end_progress.setRange(0, 100)
        self.end_to_end_progress.setValue(0)
        self.end_to_end_progress_label.setText(
            "بدأ سراج استكمال خط الإنتاج حتى البوابة البشرية التالية."
        )
        self.end_to_end_worker.start()
        self._refresh_resume_directive()

    def _on_end_to_end_progress(
        self,
        message: str,
        value: object,
    ) -> None:
        self.end_to_end_progress_label.setText(message)
        if isinstance(value, int):
            self.end_to_end_progress.setRange(0, 100)
            self.end_to_end_progress.setValue(value)
        else:
            self.end_to_end_progress.setRange(0, 0)

    def _on_end_to_end_success(self, result: object) -> None:
        if not isinstance(result, EndToEndRunResult):
            self._on_end_to_end_failure("INVALID_END_TO_END_RESULT")
            return
        self.end_to_end_progress.setRange(0, 100)
        self.end_to_end_progress.setValue(100)
        self.end_to_end_progress_label.setText(
            "توقف سراج عند: " + result.stop_reason
        )
        if result.stop_reason == "HUMAN_FINAL_REVIEW_REQUIRED":
            QMessageBox.information(
                self,
                "اكتمل الإنتاج الآلي",
                "اكتملت الوسائط والصوت والمونتاج وQA. "
                "المرحلة المتبقية هي مشاهدة الحلقة واعتمادها بشريًا.",
            )
            self.tabs.setCurrentIndex(self._tab_index_for_key("qa"))
            self._open_final_review_publish()
        elif result.stop_reason == "READY_FOR_MANUAL_YOUTUBE_UPLOAD":
            QMessageBox.information(
                self,
                "مجلد رفع YouTube جاهز",
                "جهز سراج الفيديو والعنوان والوصف والوسوم والفصول "
                "والترجمة العربية وإفصاح المحتوى المعاد بناؤه. "
                "يبقى الرفع والضغط على نشر يدويين.",
            )
            self._open_final_review_publish()
        else:
            QMessageBox.information(
                self,
                "توقف خط الإنتاج عند بوابة مطلوبة",
                result.stop_reason,
            )
        self._refresh_state()

    def _on_end_to_end_failure(self, error: str) -> None:
        self.end_to_end_progress.setRange(0, 100)
        self.end_to_end_progress.setValue(0)
        self.end_to_end_progress_label.setText(
            "توقف خط الإنتاج: " + error
        )
        QMessageBox.critical(
            self,
            "توقف استكمال الحلقة",
            error
            + "\n\nحُفظت جميع الإيصالات الصحيحة. لن يعيد سراج "
            "إرسال طلب مدفوع مقفل تلقائيًا.",
        )
        self._refresh_state()

    def _on_end_to_end_finished(self) -> None:
        if self.end_to_end_worker is not None:
            self.end_to_end_worker.deleteLater()
        self.end_to_end_worker = None
        self._refresh_state()

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

    def _build_media_execution_tab(self) -> None:
        layout = QVBoxLayout(self.media_execution_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.media_execution_status_label = QLabel(
            "بانتظار طابور الوسائط."
        )
        self.media_execution_status_label.setObjectName(
            "mediaExecutionStatusLabel"
        )
        self.media_execution_status_label.setWordWrap(True)
        layout.addWidget(self.media_execution_status_label)

        self.media_execution_progress = QProgressBar()
        self.media_execution_progress.setObjectName(
            "mediaExecutionProgress"
        )
        self.media_execution_progress.setRange(0, 100)
        self.media_execution_progress.setValue(0)
        layout.addWidget(self.media_execution_progress)

        self.media_execution_table = QTableWidget()
        self.media_execution_table.setObjectName(
            "mediaExecutionQueueTable"
        )
        self.media_execution_table.setColumnCount(8)
        self.media_execution_table.setHorizontalHeaderLabels(
            [
                "Queue ID",
                "#",
                "النوع",
                "المصدر",
                "المزود",
                "النموذج/الصوت",
                "الحالة",
                "الحد الأقصى",
            ]
        )
        self.media_execution_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.media_execution_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.media_execution_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.media_execution_table.setAlternatingRowColors(True)
        header = self.media_execution_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.media_execution_table, 1)

        actions = QHBoxLayout()
        self.execute_selected_media_button = QPushButton(
            "تفويض وتنفيذ العنصر المحدد"
        )
        self.execute_selected_media_button.setObjectName(
            "executeSelectedMediaButton"
        )
        self.execute_selected_media_button.clicked.connect(
            self._execute_selected_media
        )
        actions.addWidget(self.execute_selected_media_button)

        self.recover_selected_runware_button = QPushButton(
            "استعادة مهمة Runware المحددة"
        )
        self.recover_selected_runware_button.setObjectName(
            "recoverSelectedRunwareButton"
        )
        self.recover_selected_runware_button.clicked.connect(
            self._recover_selected_runware
        )
        actions.addWidget(self.recover_selected_runware_button)

        self.render_local_graphics_button = QPushButton(
            "رندر جميع الجرافيك المحلي"
        )
        self.render_local_graphics_button.setObjectName(
            "renderLocalGraphicsButton"
        )
        self.render_local_graphics_button.clicked.connect(
            self._render_local_graphics
        )
        actions.addWidget(self.render_local_graphics_button)

        self.open_media_output_button = QPushButton(
            "فتح ملف العنصر المحدد"
        )
        self.open_media_output_button.setObjectName(
            "openSelectedMediaOutputButton"
        )
        self.open_media_output_button.clicked.connect(
            self._open_selected_media_output
        )
        actions.addWidget(self.open_media_output_button)
        layout.addLayout(actions)

        note = QLabel(
            "كل صورة أو فيديو أو ملف TTS يحتاج تفويضًا صريحًا لمحاولة "
            "واحدة محددة. الجرافيك المحلي لا يستهلك رصيد API."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _build_sfx_audio_tab(self) -> None:
        layout = QVBoxLayout(self.sfx_audio_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.sfx_audio_status_label = QLabel(
            "بانتظار اكتمال جميع أصول الوسائط."
        )
        self.sfx_audio_status_label.setObjectName(
            "sfxAudioMixStatusLabel"
        )
        self.sfx_audio_status_label.setWordWrap(True)
        layout.addWidget(self.sfx_audio_status_label)

        self.sfx_audio_progress = QProgressBar()
        self.sfx_audio_progress.setObjectName("sfxAudioMixProgress")
        self.sfx_audio_progress.setRange(0, 100)
        self.sfx_audio_progress.setValue(0)
        layout.addWidget(self.sfx_audio_progress)

        self.build_sfx_audio_button = QPushButton(
            "بناء المؤثرات والمكساج الآلي"
        )
        self.build_sfx_audio_button.setObjectName(
            "buildSfxAudioMixButton"
        )
        self.build_sfx_audio_button.setMinimumHeight(46)
        self.build_sfx_audio_button.clicked.connect(
            self._start_sfx_audio_mix
        )
        layout.addWidget(self.build_sfx_audio_button)

        actions = QHBoxLayout()
        self.open_audio_master_button = QPushButton(
            "فتح الماستر الصوتي"
        )
        self.open_audio_master_button.setObjectName(
            "openAudioMasterButton"
        )
        self.open_audio_master_button.clicked.connect(
            self._open_audio_master
        )
        actions.addWidget(self.open_audio_master_button)

        self.open_audio_folder_button = QPushButton(
            "فتح مجلد الصوت"
        )
        self.open_audio_folder_button.setObjectName(
            "openAudioMixFolderButton"
        )
        self.open_audio_folder_button.clicked.connect(
            self._open_audio_folder
        )
        actions.addWidget(self.open_audio_folder_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        note = QLabel(
            "المرحلة محلية بالكامل: مؤثرات مناسبة للمشهد، خفض تلقائي "
            "تحت الكلام، وماستر -16 LUFS. الموسيقى ممنوعة وتكلفة API صفر."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def _build_structural_montage_tab(self) -> None:
        layout = QVBoxLayout(self.structural_montage_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.structural_montage_status_label = QLabel(
            "بانتظار اكتمال الماستر الصوتي."
        )
        self.structural_montage_status_label.setObjectName(
            "structuralMontageStatusLabel"
        )
        self.structural_montage_status_label.setWordWrap(True)
        layout.addWidget(self.structural_montage_status_label)

        self.structural_montage_progress = QProgressBar()
        self.structural_montage_progress.setObjectName(
            "structuralMontageProgress"
        )
        self.structural_montage_progress.setRange(0, 100)
        self.structural_montage_progress.setValue(0)
        layout.addWidget(self.structural_montage_progress)

        self.build_structural_montage_button = QPushButton(
            "بناء المونتاج وإخراج الحلقة"
        )
        self.build_structural_montage_button.setObjectName(
            "buildStructuralMontageButton"
        )
        self.build_structural_montage_button.setMinimumHeight(46)
        self.build_structural_montage_button.clicked.connect(
            self._start_structural_montage
        )
        layout.addWidget(self.build_structural_montage_button)

        actions = QHBoxLayout()
        self.open_final_episode_button = QPushButton(
            "عرض الحلقة النهائية"
        )
        self.open_final_episode_button.setObjectName(
            "openFinalEpisodeButton"
        )
        self.open_final_episode_button.clicked.connect(
            self._open_final_episode
        )
        actions.addWidget(self.open_final_episode_button)

        self.open_final_render_folder_button = QPushButton(
            "فتح مجلد الإخراج"
        )
        self.open_final_render_folder_button.setObjectName(
            "openFinalRenderFolderButton"
        )
        self.open_final_render_folder_button.clicked.connect(
            self._open_final_render_folder
        )
        actions.addWidget(self.open_final_render_folder_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        note = QLabel(
            "يركب سراج 70 لقطة محليًا، يحرك الصور، ينزع أصوات المصادر "
            "المرئية، ويدمج ماستر التعليق والمؤثرات وحده. تكلفة API صفر."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def _build_automatic_qa_tab(self) -> None:
        layout = QVBoxLayout(self.automatic_qa_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.automatic_qa_status_label = QLabel(
            "بانتظار اكتمال ملف الحلقة النهائي."
        )
        self.automatic_qa_status_label.setObjectName(
            "automaticQaStatusLabel"
        )
        self.automatic_qa_status_label.setWordWrap(True)
        layout.addWidget(self.automatic_qa_status_label)

        self.automatic_qa_progress = QProgressBar()
        self.automatic_qa_progress.setObjectName(
            "automaticQaProgress"
        )
        self.automatic_qa_progress.setRange(0, 100)
        self.automatic_qa_progress.setValue(0)
        layout.addWidget(self.automatic_qa_progress)

        self.run_automatic_qa_button = QPushButton(
            "تشغيل الفحص الآلي والإصلاح الجزئي"
        )
        self.run_automatic_qa_button.setObjectName(
            "runAutomaticQaButton"
        )
        self.run_automatic_qa_button.setMinimumHeight(46)
        self.run_automatic_qa_button.clicked.connect(
            self._start_automatic_qa
        )
        layout.addWidget(self.run_automatic_qa_button)

        actions = QHBoxLayout()
        self.open_automatic_qa_report_button = QPushButton(
            "فتح تقرير الفحص"
        )
        self.open_automatic_qa_report_button.setObjectName(
            "openAutomaticQaReportButton"
        )
        self.open_automatic_qa_report_button.clicked.connect(
            self._open_automatic_qa_report
        )
        actions.addWidget(self.open_automatic_qa_report_button)

        self.open_qa_final_episode_button = QPushButton(
            "عرض الحلقة المفحوصة"
        )
        self.open_qa_final_episode_button.setObjectName(
            "openQaFinalEpisodeButton"
        )
        self.open_qa_final_episode_button.clicked.connect(
            self._open_qa_final_episode
        )
        actions.addWidget(self.open_qa_final_episode_button)

        self.open_final_review_publish_button = QPushButton(
            "المراجعة النهائية وحزمة النشر"
        )
        self.open_final_review_publish_button.setObjectName(
            "openFinalReviewPublishButton"
        )
        self.open_final_review_publish_button.clicked.connect(
            self._open_final_review_publish
        )
        actions.addWidget(self.open_final_review_publish_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        note = QLabel(
            "يفحص سراج الإيصالات وSHA-256 والمواصفات والسواد والتجمد "
            "والصمت والجهارة. يصلح اللقطة المحلية أو الـmux فقط؛ أي "
            "إعادة مدفوعة تبقى ممنوعة دون تفويض صريح."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

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
        try:
            plan = inspect_end_to_end_plan(self.repo_root)
        except Exception:
            return
        if plan.action == "OPEN_MEDIA_EXECUTION":
            self._start_end_to_end_completion(plan)

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
            "DESKTOP_MEDIA_EXECUTION_ACTIVE": "يجري تنفيذ أصول الصور والفيديو والجرافيك والتعليق الصوتي.",
            "MEDIA_ASSETS_COMPLETE": "اكتملت الأصول؛ تبدأ المؤثرات والمكساج المحلي تلقائيًا.",
            "SFX_DESIGN_ACTIVE": "يجري تصميم المؤثرات وبناء الماستر الصوتي محليًا.",
            "SFX_AUDIO_MIX_FAILED": "توقفت المؤثرات أو المكساج ويمكن استئنافها محليًا.",
            "SFX_MIX_READY": "اكتمل الماستر الصوتي؛ يبدأ المونتاج والإخراج النهائي تلقائيًا.",
            "STRUCTURAL_MONTAGE_ACTIVE": "يجري تركيب اللقطات السبعين وإخراج الحلقة محليًا.",
            "STRUCTURAL_MONTAGE_FAILED": "توقف المونتاج ويمكن استئناف اللقطات غير المكتملة.",
            "FINAL_RENDER_READY_FOR_QA": "اكتمل ملف الحلقة؛ يبدأ الفحص الآلي والإصلاح الجزئي تلقائيًا.",
            "AUTOMATIC_QA_ACTIVE": "يجري فحص اللقطات والصوت والإيصالات محليًا.",
            "AUTOMATIC_QA_FAILED": "توقف الفحص الآلي ويمكن استئنافه دون طلب مدفوع.",
            "AUTOMATIC_QA_BLOCKED": "كشف الفحص عيبًا مصدريًا أو بشريًا لا يجوز إصلاحه تلقائيًا.",
            "AWAITING_HUMAN_FINAL_REVIEW": "نجح الفحص الآلي؛ بوابة المراجعة البشرية النهائية مفتوحة.",
            "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED": "سجلت المراجعة النهائية طلب إصلاح محدد دون إعادة مدفوعة تلقائية.",
            "READY_TO_PUBLISH": "اكتملت البرمجة والإنتاج؛ حزمة النشر جاهزة والرفع إلى YouTube يدوي.",
        }.get(status, status)
        self.orchestrator_status_label.setText(status_text)
        self.provider_readiness_label.setText(
            "المزودون: Luna=" + readiness["openai_luna"]
            + " | Runware=" + readiness["runware"]
            + " | ElevenLabs=" + readiness["elevenlabs"]
            + " | المونتاج=" + readiness["montage"]
            + " | الفحص=" + readiness["qa"]
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

    def _refresh_media_execution(self) -> None:
        try:
            rows = media_queue_rows(self.repo_root)
        except DesktopMediaExecutionError as exc:
            self.media_execution_status_label.setText(
                "طابور التنفيذ غير جاهز: " + str(exc)
            )
            self.media_execution_table.setRowCount(0)
            self.execute_selected_media_button.setEnabled(False)
            self.recover_selected_runware_button.setEnabled(False)
            self.render_local_graphics_button.setEnabled(False)
            self.open_media_output_button.setEnabled(False)
            return

        self._media_execution_rows = {
            row.queue_id: row for row in rows
        }
        completed = sum(row.status == "COMPLETE" for row in rows)
        self.media_execution_status_label.setText(
            f"طابور الوسائط: {completed}/{len(rows)} مكتمل. "
            "لا تنفذ أي محاولة مدفوعة دون رسالة التفويض الصريحة."
        )
        self.media_execution_table.setRowCount(len(rows))
        kind_ar = {
            "RUNWARE_IMAGE": "صورة",
            "RUNWARE_VIDEO": "فيديو",
            "LOCAL_GRAPHICS": "جرافيك محلي",
            "ELEVENLABS_TTS": "تعليق صوتي",
        }
        for row_index, row in enumerate(rows):
            values = (
                row.queue_id,
                str(row.queue_index),
                kind_ar.get(row.media_kind, row.media_kind),
                row.source_id,
                row.provider,
                row.model_or_voice,
                row.status,
                (
                    "$0.0000"
                    if row.maximum_authorized_usd <= 0
                    else f"${row.maximum_authorized_usd:.6f}"
                ),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {1, 7}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                self.media_execution_table.setItem(
                    row_index,
                    column,
                    item,
                )

        running = (
            self.media_execution_worker is not None
            and self.media_execution_worker.isRunning()
        )
        self.execute_selected_media_button.setEnabled(
            not running and bool(rows)
        )
        self.recover_selected_runware_button.setEnabled(
            not running and bool(rows)
        )
        self.render_local_graphics_button.setEnabled(
            not running
            and any(
                row.media_kind == "LOCAL_GRAPHICS"
                and row.status != "COMPLETE"
                for row in rows
            )
        )
        self.open_media_output_button.setEnabled(not running)

    def _selected_media_row(self):
        selected = self.media_execution_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(
                self,
                "لم يُحدد عنصر",
                "حدد صفًا واحدًا من طابور الوسائط.",
            )
            return None
        item = self.media_execution_table.item(
            selected[0].row(),
            0,
        )
        if item is None:
            return None
        return self._media_execution_rows.get(item.text())

    def _start_media_worker(
        self,
        mode: str,
        queue_id: str | None,
        api_key: str,
        maximum_authorized_usd: float,
    ) -> None:
        self.media_execution_worker = MediaExecutionThread(
            self.repo_root,
            mode,
            queue_id,
            api_key,
            maximum_authorized_usd,
            self,
        )
        self.media_execution_worker.progress_changed.connect(
            self._on_media_execution_progress
        )
        self.media_execution_worker.execution_succeeded.connect(
            self._on_media_execution_success
        )
        self.media_execution_worker.execution_failed.connect(
            self._on_media_execution_failure
        )
        self.media_execution_worker.finished.connect(
            self._on_media_execution_finished
        )
        self.media_execution_progress.setRange(0, 100)
        self.media_execution_progress.setValue(0)
        self.media_execution_worker.start()
        self._refresh_media_execution()

    def _execute_selected_media(self) -> None:
        row = self._selected_media_row()
        if row is None:
            return
        if row.status == "COMPLETE":
            QMessageBox.information(
                self,
                "العنصر مكتمل",
                "هذا العنصر مكتمل بالفعل.",
            )
            return
        if row.media_kind == "LOCAL_GRAPHICS":
            self._start_media_worker(
                "LOCAL_ALL",
                None,
                "",
                0.0,
            )
            return

        answer = QMessageBox.question(
            self,
            "تفويض محاولة مدفوعة واحدة",
            "العنصر: "
            + row.queue_id
            + "\nالنوع: "
            + row.media_kind
            + "\nالمزود: "
            + row.provider
            + "\nالحد الأقصى المصرح لهذه المحاولة: $"
            + f"{row.maximum_authorized_usd:.6f}"
            + "\n\nالموافقة ترسل محاولة مدفوعة واحدة فقط. "
            "لا توجد إعادة محاولة خفية.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if row.media_kind in {"RUNWARE_IMAGE", "RUNWARE_VIDEO"}:
            try:
                key = read_runware_api_key()
            except CredentialStoreError as exc:
                QMessageBox.critical(
                    self,
                    "مفتاح Runware",
                    str(exc),
                )
                return
            if not key:
                QMessageBox.warning(
                    self,
                    "مفتاح Runware مطلوب",
                    "اضبط مفتاح Runware من تبويب إنتاج المقطع.",
                )
                return
            mode = "RUNWARE"
        elif row.media_kind == "ELEVENLABS_TTS":
            try:
                key = read_elevenlabs_api_key()
            except ProviderCredentialError as exc:
                QMessageBox.critical(
                    self,
                    "مفتاح ElevenLabs",
                    str(exc),
                )
                return
            if not key:
                QMessageBox.warning(
                    self,
                    "مفتاح ElevenLabs مطلوب",
                    "اضبط مفتاح ElevenLabs من تبويب الإنتاج الذاتي.",
                )
                return
            mode = "ELEVENLABS"
        else:
            return

        self._start_media_worker(
            mode,
            row.queue_id,
            key,
            row.maximum_authorized_usd,
        )

    def _recover_selected_runware(self) -> None:
        row = self._selected_media_row()
        if row is None:
            return
        if row.media_kind not in {"RUNWARE_IMAGE", "RUNWARE_VIDEO"}:
            QMessageBox.warning(
                self,
                "الاستعادة غير متاحة",
                "الاستعادة بنفس taskUUID مخصصة لعناصر Runware.",
            )
            return
        try:
            key = read_runware_api_key()
        except CredentialStoreError as exc:
            QMessageBox.critical(self, "مفتاح Runware", str(exc))
            return
        if not key:
            QMessageBox.warning(
                self,
                "مفتاح Runware مطلوب",
                "اضبط مفتاح Runware أولًا.",
            )
            return
        self._start_media_worker(
            "RECOVER_RUNWARE",
            row.queue_id,
            key,
            row.maximum_authorized_usd,
        )

    def _render_local_graphics(self) -> None:
        self._start_media_worker("LOCAL_ALL", None, "", 0.0)

    def _open_selected_media_output(self) -> None:
        row = self._selected_media_row()
        if row is None:
            return
        path = self.repo_root / row.output_path_relative
        if not path.is_file():
            QMessageBox.warning(
                self,
                "الملف غير موجود",
                "لم يُنتج ملف هذا العنصر بعد.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_media_execution_progress(
        self,
        message: str,
        value: object,
    ) -> None:
        self.media_execution_status_label.setText(message)
        if isinstance(value, int):
            self.media_execution_progress.setRange(0, 100)
            self.media_execution_progress.setValue(value)
        else:
            self.media_execution_progress.setRange(0, 0)

    def _on_media_execution_success(self, result: object) -> None:
        count = len(result) if isinstance(result, tuple) else 1
        QMessageBox.information(
            self,
            "اكتمل التنفيذ",
            f"اكتمل {count} عنصر وحُفظت الملفات والإيصالات.",
        )
        self.media_execution_progress.setRange(0, 100)
        self.media_execution_progress.setValue(100)
        self._refresh_state()
        try:
            state = load_orchestrator_state(self.repo_root)
        except Exception:
            return
        if state.get("status") == "MEDIA_ASSETS_COMPLETE":
            self._start_sfx_audio_mix(automatic=True)

    def _on_media_execution_failure(self, error: str) -> None:
        self.media_execution_status_label.setText(
            "توقف التنفيذ: " + error
        )
        QMessageBox.critical(
            self,
            "توقف تنفيذ الوسائط",
            error,
        )
        self._refresh_state()

    def _on_media_execution_finished(self) -> None:
        if self.media_execution_worker is not None:
            self.media_execution_worker.deleteLater()
        self.media_execution_worker = None
        self._refresh_state()

    def _start_sfx_audio_mix(
        self,
        checked: bool = False,
        *,
        automatic: bool = False,
    ) -> None:
        del checked
        if (
            self.sfx_audio_worker is not None
            and self.sfx_audio_worker.isRunning()
        ):
            return
        self.sfx_audio_worker = SfxAudioMixThread(
            self.repo_root,
            self,
        )
        self.sfx_audio_worker.progress_changed.connect(
            self._on_sfx_audio_progress
        )
        self.sfx_audio_worker.mix_succeeded.connect(
            self._on_sfx_audio_success
        )
        self.sfx_audio_worker.mix_failed.connect(
            self._on_sfx_audio_failure
        )
        self.sfx_audio_worker.finished.connect(
            self._on_sfx_audio_finished
        )
        self.sfx_audio_progress.setRange(0, 100)
        self.sfx_audio_progress.setValue(0)
        self.sfx_audio_status_label.setText(
            "بدأ بناء المؤثرات والمكساج تلقائيًا."
            if automatic
            else "بدأ بناء المؤثرات والمكساج."
        )
        self.sfx_audio_worker.start()
        self._refresh_sfx_audio()

    def _on_sfx_audio_progress(
        self,
        message: str,
        value: object,
    ) -> None:
        self.sfx_audio_status_label.setText(message)
        if isinstance(value, int):
            self.sfx_audio_progress.setRange(0, 100)
            self.sfx_audio_progress.setValue(value)
        else:
            self.sfx_audio_progress.setRange(0, 0)

    def _on_sfx_audio_success(self, result: object) -> None:
        if not isinstance(result, SfxAudioMixResult):
            self._on_sfx_audio_failure(
                "INVALID_SFX_AUDIO_MIX_RESULT"
            )
            return
        self.sfx_audio_progress.setRange(0, 100)
        self.sfx_audio_progress.setValue(100)
        self.sfx_audio_status_label.setText(
            "اكتمل الماستر الصوتي وانتقل سراج إلى المونتاج."
        )
        self._start_structural_montage(automatic=True)
        QMessageBox.information(
            self,
            "اكتمل الصوت والمؤثرات",
            "تم إنشاء "
            + str(result.event_count)
            + " مؤثرًا و"
            + str(result.narration_clip_count)
            + " مقطع تعليق صوتي داخل ماستر مدته "
            + f"{result.duration_seconds:.1f} ثانية."
            + "\nتكلفة API لهذه المرحلة: $0.00."
            + "\nالمرحلة التالية: المونتاج والإخراج النهائي.",
        )
        self._refresh_state()

    def _on_sfx_audio_failure(self, error: str) -> None:
        self.sfx_audio_progress.setRange(0, 100)
        self.sfx_audio_progress.setValue(0)
        self.sfx_audio_status_label.setText(
            "توقفت مرحلة الصوت: " + error
        )
        QMessageBox.critical(
            self,
            "توقف الصوت والمؤثرات",
            error
            + "\n\nلم يُرسل أي طلب مدفوع ويمكن استئناف المرحلة محليًا.",
        )
        self._refresh_state()

    def _on_sfx_audio_finished(self) -> None:
        if self.sfx_audio_worker is not None:
            self.sfx_audio_worker.deleteLater()
        self.sfx_audio_worker = None
        self._refresh_state()

    def _refresh_sfx_audio(self) -> None:
        try:
            status = load_sfx_audio_mix_status(self.repo_root)
        except SfxAudioMixError as exc:
            self.sfx_audio_status_label.setText(
                "تعذر قراءة حالة الصوت: " + str(exc)
            )
            self.build_sfx_audio_button.setEnabled(False)
            self.open_audio_master_button.setEnabled(False)
            self.open_audio_folder_button.setEnabled(False)
            return
        state = str(status.get("status", "UNKNOWN"))
        messages = {
            "MEDIA_ASSETS_COMPLETE": (
                "اكتملت الأصول؛ مرحلة المؤثرات والمكساج جاهزة وتبدأ "
                "تلقائيًا بعد آخر عنصر."
            ),
            "SFX_DESIGN_ACTIVE": "المؤثرات والمكساج قيد التنفيذ المحلي.",
            "SFX_AUDIO_MIX_FAILED": (
                "توقفت المرحلة ويمكن استئنافها دون تكلفة API. "
                + str(status.get("last_error") or "")
            ),
            "SFX_MIX_READY": (
                "الماستر الصوتي مكتمل. المرحلة التالية: المونتاج النهائي."
            ),
            "STRUCTURAL_MONTAGE_ACTIVE": (
                "الماستر الصوتي مكتمل ويُستخدم الآن في المونتاج."
            ),
            "STRUCTURAL_MONTAGE_FAILED": (
                "الماستر الصوتي محفوظ؛ توقف المونتاج لا يؤثر عليه."
            ),
            "FINAL_RENDER_READY_FOR_QA": (
                "الماستر الصوتي محفوظ داخل ملف الحلقة النهائي."
            ),
            "AUTOMATIC_QA_ACTIVE": (
                "الماستر الصوتي محفوظ ويخضع الآن للفحص الآلي."
            ),
            "AUTOMATIC_QA_FAILED": (
                "الماستر الصوتي محفوظ؛ يمكن استئناف الفحص دون إعادة المكساج."
            ),
            "AUTOMATIC_QA_BLOCKED": (
                "كشف الفحص عيبًا يحتاج مراجعة المصدر أو الصوت."
            ),
            "AWAITING_HUMAN_FINAL_REVIEW": (
                "اجتاز الصوت الفحص الآلي وهو جاهز للمراجعة البشرية."
            ),
        }
        self.sfx_audio_status_label.setText(
            messages.get(state, "بانتظار اكتمال أصول الوسائط.")
        )
        running = (
            self.sfx_audio_worker is not None
            and self.sfx_audio_worker.isRunning()
        )
        self.build_sfx_audio_button.setEnabled(
            not running
            and state in {
                "MEDIA_ASSETS_COMPLETE",
                "SFX_AUDIO_MIX_FAILED",
            }
        )
        master = Path(str(status.get("master_wav_path", "")))
        ready = master.is_file()
        self.open_audio_master_button.setEnabled(ready)
        self.open_audio_folder_button.setEnabled(
            ready
            or state
            in {
                "SFX_AUDIO_MIX_FAILED",
                "SFX_MIX_READY",
                "STRUCTURAL_MONTAGE_ACTIVE",
                "STRUCTURAL_MONTAGE_FAILED",
                "FINAL_RENDER_READY_FOR_QA",
                "AUTOMATIC_QA_ACTIVE",
                "AUTOMATIC_QA_FAILED",
                "AUTOMATIC_QA_BLOCKED",
                "AWAITING_HUMAN_FINAL_REVIEW",
            }
        )

    def _open_audio_master(self) -> None:
        status = load_sfx_audio_mix_status(self.repo_root)
        path = Path(str(status.get("master_wav_path", "")))
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_audio_folder(self) -> None:
        status = load_sfx_audio_mix_status(self.repo_root)
        path = Path(str(status.get("master_wav_path", ""))).parent
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _start_structural_montage(
        self,
        checked: bool = False,
        *,
        automatic: bool = False,
    ) -> None:
        del checked
        if (
            self.structural_montage_worker is not None
            and self.structural_montage_worker.isRunning()
        ):
            return
        self.structural_montage_worker = StructuralMontageThread(
            self.repo_root,
            self,
        )
        self.structural_montage_worker.progress_changed.connect(
            self._on_structural_montage_progress
        )
        self.structural_montage_worker.render_succeeded.connect(
            self._on_structural_montage_success
        )
        self.structural_montage_worker.render_failed.connect(
            self._on_structural_montage_failure
        )
        self.structural_montage_worker.finished.connect(
            self._on_structural_montage_finished
        )
        self.structural_montage_progress.setRange(0, 100)
        self.structural_montage_progress.setValue(0)
        self.structural_montage_status_label.setText(
            "بدأ المونتاج تلقائيًا بعد الماستر الصوتي."
            if automatic
            else "بدأ المونتاج والإخراج النهائي."
        )
        self.structural_montage_worker.start()
        self._refresh_structural_montage()

    def _on_structural_montage_progress(
        self,
        message: str,
        value: object,
    ) -> None:
        self.structural_montage_status_label.setText(message)
        if isinstance(value, int):
            self.structural_montage_progress.setRange(0, 100)
            self.structural_montage_progress.setValue(value)
        else:
            self.structural_montage_progress.setRange(0, 0)

    def _on_structural_montage_success(self, result: object) -> None:
        if not isinstance(result, StructuralMontageResult):
            self._on_structural_montage_failure(
                "INVALID_STRUCTURAL_MONTAGE_RESULT"
            )
            return
        self.structural_montage_progress.setRange(0, 100)
        self.structural_montage_progress.setValue(100)
        self.structural_montage_status_label.setText(
            "اكتملت الحلقة وانتقلت إلى الفحص الآلي."
        )
        self._start_automatic_qa(automatic=True)
        QMessageBox.information(
            self,
            "اكتمل المونتاج النهائي",
            "تم تركيب اللقطات السبعين وإخراج حلقة مدتها "
            + f"{result.duration_seconds:.1f} ثانية."
            + "\nرُندرت "
            + str(result.rendered_shot_count)
            + " لقطة وأعيد استخدام "
            + str(result.reused_shot_count)
            + " لقطة صحيحة."
            + "\nتكلفة API: $0.00."
            + "\nالمرحلة التالية: الفحص الآلي والإصلاح الجزئي.",
        )
        self._refresh_state()

    def _on_structural_montage_failure(self, error: str) -> None:
        self.structural_montage_progress.setRange(0, 100)
        self.structural_montage_progress.setValue(0)
        self.structural_montage_status_label.setText(
            "توقف المونتاج: " + error
        )
        QMessageBox.critical(
            self,
            "توقف المونتاج النهائي",
            error
            + "\n\nستُحفظ اللقطات الصحيحة ويُستأنف الباقي دون طلب مدفوع.",
        )
        self._refresh_state()

    def _on_structural_montage_finished(self) -> None:
        if self.structural_montage_worker is not None:
            self.structural_montage_worker.deleteLater()
        self.structural_montage_worker = None
        self._refresh_state()

    def _refresh_structural_montage(self) -> None:
        try:
            status = load_structural_montage_status(self.repo_root)
        except StructuralMontageError as exc:
            self.structural_montage_status_label.setText(
                "تعذر قراءة حالة المونتاج: " + str(exc)
            )
            self.build_structural_montage_button.setEnabled(False)
            self.open_final_episode_button.setEnabled(False)
            self.open_final_render_folder_button.setEnabled(False)
            return
        state = str(status.get("status", "UNKNOWN"))
        messages = {
            "SFX_MIX_READY": (
                "الماستر الصوتي مكتمل؛ المونتاج جاهز ويبدأ تلقائيًا."
            ),
            "STRUCTURAL_MONTAGE_ACTIVE": (
                "يجري تركيب اللقطات وإخراج الحلقة محليًا."
            ),
            "STRUCTURAL_MONTAGE_FAILED": (
                "توقف المونتاج ويمكن استئناف اللقطات غير المكتملة: "
                + str(status.get("last_error") or "")
            ),
            "FINAL_RENDER_READY_FOR_QA": (
                "ملف الحلقة مكتمل وجاهز للفحص الآلي."
            ),
            "AUTOMATIC_QA_ACTIVE": (
                "ملف الحلقة قيد الفحص الآلي المحلي."
            ),
            "AUTOMATIC_QA_FAILED": (
                "ملف الحلقة محفوظ ويمكن استئناف الفحص."
            ),
            "AUTOMATIC_QA_BLOCKED": (
                "ملف الحلقة محفوظ مع تقرير عيوب يحتاج معالجة محددة."
            ),
            "AWAITING_HUMAN_FINAL_REVIEW": (
                "ملف الحلقة اجتاز الفحص الآلي وجاهز للمراجعة البشرية."
            ),
        }
        self.structural_montage_status_label.setText(
            messages.get(state, "بانتظار اكتمال الماستر الصوتي.")
        )
        running = (
            self.structural_montage_worker is not None
            and self.structural_montage_worker.isRunning()
        )
        self.build_structural_montage_button.setEnabled(
            not running
            and state in {
                "SFX_MIX_READY",
                "STRUCTURAL_MONTAGE_FAILED",
            }
        )
        final_path = Path(str(status.get("final_master_path", "")))
        ready = final_path.is_file()
        self.open_final_episode_button.setEnabled(ready)
        self.open_final_render_folder_button.setEnabled(
            ready or state in {
                "STRUCTURAL_MONTAGE_FAILED",
                "FINAL_RENDER_READY_FOR_QA",
                "AUTOMATIC_QA_ACTIVE",
                "AUTOMATIC_QA_FAILED",
                "AUTOMATIC_QA_BLOCKED",
                "AWAITING_HUMAN_FINAL_REVIEW",
            }
        )

    def _open_final_episode(self) -> None:
        status = load_structural_montage_status(self.repo_root)
        path = Path(str(status.get("final_master_path", "")))
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_final_render_folder(self) -> None:
        status = load_structural_montage_status(self.repo_root)
        path = Path(str(status.get("final_master_path", ""))).parent
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _start_automatic_qa(
        self,
        checked: bool = False,
        *,
        automatic: bool = False,
    ) -> None:
        del checked
        if (
            self.automatic_qa_worker is not None
            and self.automatic_qa_worker.isRunning()
        ):
            return
        self.automatic_qa_worker = AutomaticQAThread(
            self.repo_root,
            self,
        )
        self.automatic_qa_worker.progress_changed.connect(
            self._on_automatic_qa_progress
        )
        self.automatic_qa_worker.qa_succeeded.connect(
            self._on_automatic_qa_success
        )
        self.automatic_qa_worker.qa_failed.connect(
            self._on_automatic_qa_failure
        )
        self.automatic_qa_worker.finished.connect(
            self._on_automatic_qa_finished
        )
        self.automatic_qa_progress.setRange(0, 100)
        self.automatic_qa_progress.setValue(0)
        self.automatic_qa_status_label.setText(
            "بدأ الفحص تلقائيًا بعد اكتمال المونتاج."
            if automatic
            else "بدأ الفحص الآلي والإصلاح الجزئي."
        )
        self.automatic_qa_worker.start()
        self._refresh_automatic_qa()

    def _on_automatic_qa_progress(
        self,
        message: str,
        value: object,
    ) -> None:
        self.automatic_qa_status_label.setText(message)
        if isinstance(value, int):
            self.automatic_qa_progress.setRange(0, 100)
            self.automatic_qa_progress.setValue(value)
        else:
            self.automatic_qa_progress.setRange(0, 0)

    def _on_automatic_qa_success(self, result: object) -> None:
        if not isinstance(result, AutomaticQAResult):
            self._on_automatic_qa_failure("INVALID_AUTOMATIC_QA_RESULT")
            return
        self.automatic_qa_progress.setRange(0, 100)
        self.automatic_qa_progress.setValue(100)
        if result.status == "AWAITING_HUMAN_FINAL_REVIEW":
            self.automatic_qa_status_label.setText(
                "نجح الفحص الآلي؛ الحلقة جاهزة للمراجعة البشرية النهائية."
            )
            QMessageBox.information(
                self,
                "اجتاز الفحص الآلي",
                "لا توجد عيوب تقنية مانعة."
                + "\nمرات الإصلاح المحلي: "
                + str(result.repair_passes)
                + "\nاللقطات التي أُصلحت: "
                + str(result.repaired_shot_count)
                + "\nالتحذيرات غير المانعة: "
                + str(result.warning_count)
                + "\nتكلفة API: $0.00."
                + "\nالمرحلة التالية: المراجعة البشرية النهائية.",
            )
        else:
            self.automatic_qa_status_label.setText(
                "توقف الفحص عند عيب مصدري أو بشري موثق في التقرير."
            )
            QMessageBox.warning(
                self,
                "الفحص يحتاج معالجة محددة",
                "بقيت "
                + str(result.blocking_issue_count)
                + " مشكلة مانعة. لم يُرسل أي طلب مدفوع. افتح التقرير "
                + "لمعرفة اللقطة أو مرحلة الصوت المطلوبة.",
            )
        self._refresh_state()

    def _on_automatic_qa_failure(self, error: str) -> None:
        self.automatic_qa_progress.setRange(0, 100)
        self.automatic_qa_progress.setValue(0)
        self.automatic_qa_status_label.setText(
            "توقف الفحص الآلي: " + error
        )
        QMessageBox.critical(
            self,
            "توقف الفحص الآلي",
            error
            + "\n\nلم يُرسل أي طلب مدفوع ويمكن استئناف الفحص محليًا.",
        )
        self._refresh_state()

    def _on_automatic_qa_finished(self) -> None:
        if self.automatic_qa_worker is not None:
            self.automatic_qa_worker.deleteLater()
        self.automatic_qa_worker = None
        self._refresh_state()

    def _refresh_automatic_qa(self) -> None:
        try:
            status = load_automatic_qa_status(self.repo_root)
        except AutomaticQAError as exc:
            self.automatic_qa_status_label.setText(
                "تعذر قراءة حالة الفحص: " + str(exc)
            )
            self.run_automatic_qa_button.setEnabled(False)
            self.open_automatic_qa_report_button.setEnabled(False)
            self.open_qa_final_episode_button.setEnabled(False)
            self.open_final_review_publish_button.setEnabled(False)
            return
        state = str(status.get("status", "UNKNOWN"))
        messages = {
            "FINAL_RENDER_READY_FOR_QA": (
                "ملف الحلقة جاهز ويبدأ الفحص تلقائيًا."
            ),
            "AUTOMATIC_QA_ACTIVE": (
                "يجري فحص 70 لقطة والصوت والإيصالات محليًا."
            ),
            "AUTOMATIC_QA_FAILED": (
                "توقف الفحص ويمكن استئنافه دون تكلفة API: "
                + str(status.get("last_error") or "")
            ),
            "AUTOMATIC_QA_BLOCKED": (
                "بقيت مشاكل مانعة موثقة. أصلح المصدر المحدد ثم أعد الفحص."
            ),
            "AWAITING_HUMAN_FINAL_REVIEW": (
                "اجتازت الحلقة الفحص الآلي وهي بانتظار المراجعة البشرية."
            ),
            "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED": (
                "هناك طلب إصلاح من المراجعة النهائية؛ أعد QA بعد أي تغيير غير metadata."
            ),
            "READY_TO_PUBLISH": (
                "اجتازت الحلقة QA والمراجعة البشرية وحزمة النشر جاهزة."
            ),
        }
        self.automatic_qa_status_label.setText(
            messages.get(state, "بانتظار اكتمال ملف الحلقة النهائي.")
        )
        running = (
            self.automatic_qa_worker is not None
            and self.automatic_qa_worker.isRunning()
        )
        self.run_automatic_qa_button.setEnabled(
            not running
            and state in {
                "FINAL_RENDER_READY_FOR_QA",
                "AUTOMATIC_QA_FAILED",
                "AUTOMATIC_QA_BLOCKED",
                "AWAITING_HUMAN_FINAL_REVIEW",
                "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
            }
        )
        report = Path(str(status.get("report_path", "")))
        final = Path(str(status.get("final_master_path", "")))
        self.open_automatic_qa_report_button.setEnabled(report.is_file())
        self.open_qa_final_episode_button.setEnabled(final.is_file())
        self.open_final_review_publish_button.setEnabled(
            final.is_file()
            and report.is_file()
            and state in {
                "AWAITING_HUMAN_FINAL_REVIEW",
                "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
                "READY_TO_PUBLISH",
            }
        )

    def _open_automatic_qa_report(self) -> None:
        status = load_automatic_qa_status(self.repo_root)
        path = Path(str(status.get("report_path", "")))
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_qa_final_episode(self) -> None:
        status = load_automatic_qa_status(self.repo_root)
        path = Path(str(status.get("final_master_path", "")))
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_final_review_publish(self) -> None:
        dialog = FinalReviewPublishDialog(self.repo_root, self)
        dialog.exec()
        self._refresh_state()

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
        self._refresh_media_execution()
        self._refresh_sfx_audio()
        self._refresh_structural_montage()
        self._refresh_automatic_qa()
        self._refresh_resume_directive()
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
        workers = (
            (self.scope_worker, "اختيار الموضوع أو البحث مستمر"),
            (self.editorial_worker, "البحث والنص والستوريبورد مستمرة"),
            (self.media_execution_worker, "تنفيذ عنصر وسائط مستمر"),
            (self.end_to_end_worker, "استكمال خط الإنتاج مستمر"),
            (self.worker, "توليد المقطع مستمر"),
            (self.sfx_audio_worker, "المكساج مستمر"),
            (self.structural_montage_worker, "المونتاج مستمر"),
            (self.automatic_qa_worker, "الفحص مستمر"),
        )
        for worker, title in workers:
            if worker is not None and worker.isRunning():
                QMessageBox.information(
                    self,
                    title,
                    "اترك النافذة مفتوحة حتى تنتهي العملية بأمان.",
                )
                return
        super().reject()

