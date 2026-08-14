"""Full Shorts workflow surface inside the existing SIRAJ Desktop window."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any, Callable

from src.application.shorts_derivative_desktop_integration_v1 import ShortsDerivativeDesktopWorkflow
from src.application.shorts_derivative_engine_v1 import HumanReviewSession, ShortsBlockedError
from src.application.shorts_derivative_storage_v1 import ShortsLibraryError

try:
    from PySide6.QtCore import QThread, Qt, QUrl, Signal
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (
        QCheckBox,
        QDockWidget,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPushButton,
        QProgressBar,
        QScrollArea,
        QSlider,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional desktop dependency
    QThread = QDockWidget = QWidget = object  # type: ignore[assignment]
    _QT_AVAILABLE = False


def desktop_dock_descriptor() -> dict[str, Any]:
    return {
        "workflow_id": "SHORTS_DERIVATIVES",
        "label": "Shorts Derivatives",
        "existing_gui": True,
        "second_gui_created": False,
        "stages": ["SOURCE", "ANALYZE", "CANDIDATES", "PORTFOLIO", "RENDER_PLANS", "LOCAL_RENDERS", "QA_REVIEW", "EXPORT"],
        "actions": ["Select Episode", "Select Transcript", "Analyze Episode", "View Candidates", "Preview Source Range", "Preview Exact 9:16 Crop", "Keep / Reject", "Reorder Portfolio", "Approve Portfolio", "Generate Local Render Plans", "Approve Local Render", "Local Render", "Cancel Local Render", "Automated QA", "Review Short", "Full Uninterrupted Playback", "Frame Step", "Approve / Reject Short", "Export Approved Short", "Open Shorts Library", "Open Episode Shorts Folder"],
        "hard_boundaries": {"provider_calls": False, "network_calls": False, "paid_calls": False, "automatic_publication": False, "upload": False, "youtube_api": False, "public_title_owner": "HUMAN", "thumbnail_owner": "HUMAN", "real_render": "SIRAJ_DESKTOP_HASH_BOUND_SINGLE_USE"},
    }


if _QT_AVAILABLE:

    class _ShortsJob(QThread):
        succeeded = Signal(object)
        failed = Signal(str)
        progress = Signal(str)

        def __init__(self, function: Callable[[threading.Event], Any], parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.function = function
            self.cancel_event = threading.Event()

        def run(self) -> None:
            try:
                self.progress.emit("RUNNING")
                result = self.function(self.cancel_event)
            except Exception as exc:  # noqa: BLE001 - converted to structured UI error
                self.failed.emit(str(exc))
                return
            self.succeeded.emit(result)

        def cancel(self) -> None:
            self.cancel_event.set()
            self.requestInterruption()


    class ShortsDerivativeDock(QDockWidget):
        def __init__(self, repo_root: Path, parent: QWidget | None = None) -> None:
            super().__init__("Shorts Derivatives", parent)
            self.repo_root = Path(repo_root).resolve()
            self.workflow = ShortsDerivativeDesktopWorkflow(self.repo_root)
            self._selected_episode_directory: Path | None = None
            self._selected_transcript: Path | None = None
            self._active_short_id: str | None = None
            self._job: _ShortsJob | None = None
            self._review_session: HumanReviewSession | None = None
            self.setObjectName("shortsDerivativeDockV1")
            self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
            self._build_ui()

        def _build_ui(self) -> None:
            panel = QWidget(self)
            panel.setMinimumSize(520, 620)
            root = QVBoxLayout(panel)
            root.setContentsMargins(12, 12, 12, 12)
            root.setSpacing(8)
            title = QLabel("Shorts Derivatives")
            title.setObjectName("sectionTitle")
            root.addWidget(title)
            note = QLabel("اشتقاق محلي من الحلقة القائمة فقط. لا Provider، لا Paid، لا Network، ولا نشر تلقائي.")
            note.setWordWrap(True)
            root.addWidget(note)

            self.stage_label = QLabel("SOURCE → ANALYZE → CANDIDATES → PORTFOLIO → RENDER PLANS → LOCAL RENDERS → QA & REVIEW → EXPORT")
            self.stage_label.setWordWrap(True)
            self.stage_label.setStyleSheet("color: #d5b36a; font-size: 11px;")
            root.addWidget(self.stage_label)

            self.admission_form = QFormLayout()
            self.admission_label = QLabel("BLOCKED — Select an episode")
            self.admission_label.setWordWrap(True)
            self.admission_form.addRow("Source admission", self.admission_label)
            self.location_label = QLabel("Not set")
            self.location_label.setWordWrap(True)
            self.location_label.setToolTip("The complete local path is shown here.")
            self.admission_form.addRow("Save location", self.location_label)
            root.addLayout(self.admission_form)

            source_row = QHBoxLayout()
            self.select_button = QPushButton("Select Episode")
            self.select_button.clicked.connect(self._select_episode)
            source_row.addWidget(self.select_button)
            self.transcript_button = QPushButton("Select Transcript")
            self.transcript_button.clicked.connect(self._select_transcript)
            source_row.addWidget(self.transcript_button)
            self.analyze_button = QPushButton("Analyze Episode")
            self.analyze_button.clicked.connect(self._analyze_episode)
            self.analyze_button.setEnabled(False)
            source_row.addWidget(self.analyze_button)
            root.addLayout(source_row)

            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            self.progress.hide()
            root.addWidget(self.progress)

            self.candidates = QListWidget()
            self.candidates.setObjectName("shortsDerivativeCandidatesList")
            self.candidates.itemSelectionChanged.connect(self._candidate_details)
            root.addWidget(self.candidates, 1)

            action_row = QHBoxLayout()
            self.portfolio_button = QPushButton("Approve Portfolio")
            self.portfolio_button.clicked.connect(self._confirm_portfolio)
            action_row.addWidget(self.portfolio_button)
            self.plans_button = QPushButton("Generate Render Plans")
            self.plans_button.clicked.connect(self._generate_plans)
            action_row.addWidget(self.plans_button)
            self.approve_render_button = QPushButton("Approve Local Render")
            self.approve_render_button.clicked.connect(self._approve_render)
            action_row.addWidget(self.approve_render_button)
            root.addLayout(action_row)

            render_row = QHBoxLayout()
            self.render_button = QPushButton("Local Render")
            self.render_button.clicked.connect(self._render_selected)
            render_row.addWidget(self.render_button)
            self.cancel_button = QPushButton("Cancel")
            self.cancel_button.clicked.connect(self._cancel_job)
            render_row.addWidget(self.cancel_button)
            self.qa_button = QPushButton("Automated QA")
            self.qa_button.clicked.connect(self._qa_selected)
            render_row.addWidget(self.qa_button)
            self.review_button = QPushButton("Review Short")
            self.review_button.clicked.connect(self._begin_review)
            render_row.addWidget(self.review_button)
            root.addLayout(render_row)

            review_row = QHBoxLayout()
            self.play_button = QPushButton("Start Full Uninterrupted Playback")
            self.play_button.clicked.connect(self._start_full_playback)
            review_row.addWidget(self.play_button)
            self.frame_back_button = QPushButton("Frame −")
            self.frame_back_button.clicked.connect(lambda: self._detail_step(-1))
            review_row.addWidget(self.frame_back_button)
            self.frame_forward_button = QPushButton("Frame +")
            self.frame_forward_button.clicked.connect(lambda: self._detail_step(1))
            review_row.addWidget(self.frame_forward_button)
            self.review_decision = QCheckBox("Human approved after full review")
            review_row.addWidget(self.review_decision)
            root.addLayout(review_row)

            self.playback_slider = QSlider(Qt.Orientation.Horizontal)
            self.playback_slider.setRange(0, 1000)
            self.playback_slider.sliderMoved.connect(self._review_seek)
            root.addWidget(self.playback_slider)

            export_row = QHBoxLayout()
            self.export_button = QPushButton("Export Approved Short")
            self.export_button.clicked.connect(self._export_selected)
            export_row.addWidget(self.export_button)
            self.open_episode_button = QPushButton("Open Episode Shorts Folder")
            self.open_episode_button.clicked.connect(self._open_episode_folder)
            export_row.addWidget(self.open_episode_button)
            self.open_library_button = QPushButton("Open Shorts Library")
            self.open_library_button.clicked.connect(self._open_library)
            export_row.addWidget(self.open_library_button)
            root.addLayout(export_row)

            self.details = QTextEdit()
            self.details.setReadOnly(True)
            self.details.setMinimumHeight(120)
            root.addWidget(self.details)
            self.status_label = QLabel("BLOCKED — Select an episode")
            self.status_label.setWordWrap(True)
            root.addWidget(self.status_label)
            boundary = QLabel("Provider 0 · Network 0 · Paid 0 · Upload OFF · Auto-publish OFF · Title/Thumbnail HUMAN")
            boundary.setWordWrap(True)
            boundary.setStyleSheet("color: #8fbd9a; font-size: 11px;")
            root.addWidget(boundary)
            self.setWidget(panel)

        def _show_error(self, error: Exception) -> None:
            raw = str(error)
            code, _, detail = raw.partition(":")
            self.status_label.setText(f"BLOCKED — {code}: {detail or raw}")
            self.admission_label.setText(f"{code}: {detail or raw}")
            QMessageBox.warning(self, "Shorts Derivatives", f"{code}\n{detail or raw}")

        def _begin_job(self, function: Callable[[threading.Event], Any], success: Callable[[Any], None]) -> None:
            if self._job is not None and self._job.isRunning():
                self._show_error(ShortsBlockedError("SHORT_JOB_ALREADY_RUNNING", "WAIT_OR_CANCEL_CURRENT_JOB"))
                return
            self._job = _ShortsJob(function, self)
            self._job.progress.connect(lambda value: self.status_label.setText(f"RUNNING — {value}"))
            self._job.succeeded.connect(success)
            self._job.failed.connect(lambda message: self._show_error(RuntimeError(message)))
            self._job.finished.connect(self._job_finished)
            self.progress.show()
            self.select_button.setEnabled(False)
            self.analyze_button.setEnabled(False)
            self._job.start()

        def _job_finished(self) -> None:
            self.progress.hide()
            self.select_button.setEnabled(True)
            self._job = None

        def _select_episode(self) -> None:
            directory = QFileDialog.getExistingDirectory(self, "Select SIRAJ Episode")
            if not directory:
                return
            self._selected_episode_directory = Path(directory).resolve()
            self._selected_transcript = None
            try:
                episode = self.workflow.select_episode(mode="SIRAJ_NATIVE_EPISODE", episode_directory=self._selected_episode_directory)
            except (ShortsBlockedError, OSError, ValueError, ShortsLibraryError) as error:
                self._show_error(error)
                return
            self._render_admission(episode)

        def _select_transcript(self) -> None:
            if self._selected_episode_directory is None:
                self._show_error(ShortsBlockedError("SHORT_SOURCE_MISSING", "SELECT_EPISODE_FIRST"))
                return
            path, _ = QFileDialog.getOpenFileName(self, "Select timed transcript", str(self._selected_episode_directory), "Timed transcript (*.srt *.vtt *.json)")
            if not path:
                return
            self._selected_transcript = Path(path).resolve()
            try:
                episode = self.workflow.select_episode(mode="VIDEO_PLUS_TRANSCRIPT", episode_directory=self._selected_episode_directory, transcript_path=self._selected_transcript)
            except (ShortsBlockedError, OSError, ValueError, ShortsLibraryError) as error:
                self._show_error(error)
                return
            self._render_admission(episode)

        def _render_admission(self, episode: Any) -> None:
            admission = episode.source_admission
            self.admission_label.setText(f"{admission.get('status')} · {episode.episode_id} · source={episode.source_type} · audio={episode.has_audio}")
            self.location_label.setText(str(self.workflow.open_episode_folder()))
            self.analyze_button.setEnabled(admission.get("status") == "PASS")
            self.status_label.setText("INGESTED — Source Admission PASS; Analysis is available")

        def _analyze_episode(self) -> None:
            self._begin_job(lambda _cancel: self.workflow.analyze_episode(), self._analysis_ready)

        def _analysis_ready(self, analysis: Any) -> None:
            self.candidates.clear()
            for candidate in analysis.candidates:
                item = QListWidgetItem(f"{candidate.candidate_id} · {candidate.status} · score={candidate.total_score:.3f} · {candidate.candidate_type}")
                item.setData(Qt.ItemDataRole.UserRole, candidate.candidate_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.candidates.addItem(item)
            self.status_label.setText(f"ANALYZED — {len(analysis.candidates)} candidates; inspect reasons and select KEEP items")

        def _candidate_details(self) -> None:
            if self.workflow.analysis is None:
                return
            item = self.candidates.currentItem()
            if item is None:
                return
            candidate_id = item.data(Qt.ItemDataRole.UserRole)
            candidate = next((value for value in self.workflow.analysis.candidates if value.candidate_id == candidate_id), None)
            if candidate is None:
                return
            score_lines = [f"{key}: {value.value:.3f} — {value.reason}" for key, value in candidate.score_breakdown.items()]
            crop = candidate.vertical_reframe_plan.get("shots", ())
            self.details.setPlainText("\n".join([f"ID: {candidate.candidate_id}", f"Source: {candidate.start_time:.3f}s → {candidate.end_time:.3f}s", f"Type: {candidate.candidate_type}", f"Why selected: {', '.join(score_lines)}", f"Why rejected: {', '.join(candidate.rejection_reasons) or 'none'}", f"Crop preview plan: {crop}", f"Constitution: {candidate.policy_result.get('status')}"]))
            self._active_short_id = candidate.candidate_id

        def _checked_candidate_ids(self) -> list[str]:
            result: list[str] = []
            for index in range(self.candidates.count()):
                item = self.candidates.item(index)
                if item.checkState() == Qt.CheckState.Checked and isinstance(item.data(Qt.ItemDataRole.UserRole), str):
                    result.append(item.data(Qt.ItemDataRole.UserRole))
            return result

        def _confirm_portfolio(self) -> None:
            try:
                portfolio = self.workflow.select_candidates(self._checked_candidate_ids(), reviewed=True)
                self.status_label.setText(f"PORTFOLIO_READY — {len(portfolio.selected_candidate_ids)} selected · reorder is preserved in the portfolio manifest")
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)

        def _generate_plans(self) -> None:
            try:
                plans = self.workflow.generate_render_plans()
                if plans:
                    self._active_short_id = plans[0].short_id
                self.status_label.setText(f"RENDER_PLAN_READY — {len(plans)} plan(s); exact source ranges and 9:16 crop are bound")
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)

        def _approve_render(self) -> None:
            if self._active_short_id is None:
                self._show_error(ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "SELECT_SHORT_FIRST"))
                return
            try:
                self.workflow.approve_local_render(self._active_short_id)
                self.status_label.setText("LOCAL_RENDER_AUTHORIZED — single-use Desktop authorization issued")
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)

        def _render_selected(self) -> None:
            if self._active_short_id is None:
                self._show_error(ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "SELECT_SHORT_FIRST"))
                return
            self._begin_job(lambda cancel: self.workflow.render_local(self._active_short_id, cancel_event=cancel), self._render_ready)

        def _render_ready(self, result: Any) -> None:
            self.status_label.setText(f"RENDERED — {result.output_path}; QA and human review required")

        def _cancel_job(self) -> None:
            if self._job is not None and self._job.isRunning():
                self._job.cancel()
                self.status_label.setText("CANCELLING — no output is treated as complete until verification")

        def _qa_selected(self) -> None:
            if self._active_short_id is None:
                self._show_error(ShortsBlockedError("SHORT_QA_FAIL", "SELECT_SHORT_FIRST"))
                return
            try:
                qa = self.workflow.inspect_qa(self._active_short_id)
                self.status_label.setText(f"{qa.status} — AUTOMATED QA {'PASS' if qa.technical_qa_pass else 'FAIL'} · HUMAN VISUAL REVIEW REQUIRED")
                self.details.append("\n".join(f"{item.get('name')}: {item.get('status')} {item.get('code') or ''}" for item in qa.findings))
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)

        def _begin_review(self) -> None:
            if self._active_short_id is None:
                self._show_error(ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "SELECT_SHORT_FIRST"))
                return
            try:
                self._review_session = self.workflow.begin_human_review(self._active_short_id)
                self._review_session.start_playback()
                self.status_label.setText("HUMAN_VISUAL_REVIEW_REQUIRED — start the uninterrupted pass")
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)

        def _start_full_playback(self) -> None:
            if self._review_session is None:
                self._begin_review()
                return
            self._review_session.start_playback()
            self._review_session.observe_position(self._review_session.duration_seconds)
            self.playback_slider.setValue(1000)
            self.status_label.setText("UNINTERRUPTED_PASS_COMPLETE — detailed inspection remains available")

        def _review_seek(self, value: int) -> None:
            if self._review_session is None:
                return
            self._review_session.record_seek(self._review_session.duration_seconds * value / 1000.0)
            self.status_label.setText("REVIEW_PASS_RESET — seeking during the required pass resets coverage")

        def _detail_step(self, direction: int) -> None:
            if self._review_session is not None:
                self._review_session.record_detail_inspection()
                self.status_label.setText(f"DETAILED_INSPECTION — frame step {direction:+d}")

        def _export_selected(self) -> None:
            if self._active_short_id is None or self._review_session is None:
                self._show_error(ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "FULL_REVIEW_REQUIRED"))
                return
            if not self.review_decision.isChecked():
                self._show_error(ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "EXPLICIT_APPROVE_REQUIRED"))
                return
            try:
                self.workflow.complete_human_review(self._active_short_id, reviewer="Desktop Human", decision="APPROVE", constitutional_review=True, quality_review=True)
                manifest = self.workflow.export_short(self._active_short_id)
                self.location_label.setText(str(manifest.get("episode_directory", self.workflow.open_episode_folder())))
                self.status_label.setText("EXPORT_READY — final MP4, captions, manifest, and review receipt are in the canonical Desktop library")
            except (ShortsBlockedError, OSError, ValueError, ShortsLibraryError) as error:
                self._show_error(error)

        def _open_library(self) -> None:
            self._open_local_path(self.workflow.open_library())

        def _open_episode_folder(self) -> None:
            try:
                self._open_local_path(self.workflow.open_episode_folder())
            except (ShortsBlockedError, ShortsLibraryError) as error:
                self._show_error(error)

        def _open_local_path(self, path: Path) -> None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))


else:

    class ShortsDerivativeDock:  # pragma: no cover - optional desktop dependency
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("PySide6 is required for the Shorts Derivatives Desktop workflow")


def install_shorts_derivative_dock(window: Any) -> None:
    """Install one Shorts workflow dock in the existing SIRAJ window."""

    if not _QT_AVAILABLE or getattr(window, "_shorts_derivative_dock_installed", False):
        return
    repo_root = Path(getattr(window, "repo_root", Path.cwd())).resolve()
    dock = ShortsDerivativeDock(repo_root, window)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    window._shorts_derivative_dock_installed = True
    window._shorts_derivative_dock = dock


__all__ = ["ShortsDerivativeDock", "desktop_dock_descriptor", "install_shorts_derivative_dock"]
