"""Professional V6 integration for the ORIGINAL SIRAJ desktop dashboard.

The existing SirajDesktopWindow remains the application. This module adds an
embedded V6 command center and upgrades the existing workflow / approvals /
video / settings pages to read canonical V6 state.
"""

from __future__ import annotations
# SIRAJ_R9_1_1_ADAPTIVE_RESUME_WORKER_TELEMETRY
from src.application.siraj_live_telemetry_v6_6_r9 import emit_event
from src.application.worker_lifecycle_v1 import WorkerLifecycle, WorkerState
from src.application.qt_worker_contracts import validate_monitor_contract

import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import COLORS
# SIRAJ_R9_TELEMETRY_UI_IMPORT
from src.application.siraj_live_telemetry_v6_6_r9 import (
    live_paths,
    read_live_state,
    recent_events,
)
from .widgets import Panel, StatusPill
from .v6_dashboard_state_adapter import (
    V6_STAGE_AR,
    build_v6_dashboard_snapshot,
    install_v6_stage_label_bridge,
)

from src.application.siraj_series_autopilot_v6_0_1 import STAGES
from src.application.episode_transition_ledger_v1 import BASE_STAGE_ORDER
from src.application.desktop_media_cost_preflight_v1 import (
    MediaCostPreflightError,
    read_persisted_media_cost_preflight,
)
from src.application.siraj_production_composition_root import (
    EVENTS_REVIEW_STAGE,
    authorize_current_stage,
    authorization_phrase_for,
    full_episode_authorization_active,
    inspect_autopilot,
    master_auth_path,
    run_until_gate,
)
from src.application.siraj_event_review_v6_6 import (
    approve_events,
    conversation_entries,
    discuss_events_with_luna,
    events_approved,
    load_event_plan,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    FULL_EPISODE_CONFIRMATION_PHRASE,
    PAID_RETRY_CONFIRMATION_PHRASE,
)

MACRO_LABELS = (
    "البحث والمصادر",
    "القصة والنص",
    "النطق والصوت",
    "الستوريبورد والبرومبت",
    "توليد الوسائط",
    "المونتاج والجودة",
    "المراجعة البشرية",
)

MACRO_STAGE_INDEX = {
    "TOPIC_SELECTION": 0,
    "SOURCE_RESEARCH_FROM_ZERO": 0,
    "SOURCE_CLAIM_MATRIX": 0,
    "EVENTS_REVIEW_AND_APPROVAL": 1,
    "STORY_ARCHITECTURE": 1,
    "ICONIC_CINEMATIC_REVIEW": 1,
    "FINAL_SCRIPT": 1,
    "PRONUNCIATION_AND_PERFORMANCE_GATE": 2,
    "FINAL_TTS": 2,
    "AUDIO_TIMESTAMPS_AND_BEATS": 2,
    "AUDIO_BOUND_STORYBOARD": 3,
    "LUNA_SEMANTIC_PROMPT_DIRECTION": 3,
    "NARRATION_VISUAL_ALIGNMENT_GATE": 3,
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE": 3,
    "MEDIA_COST_PREFLIGHT": 4,
    "PROVIDER_EXECUTION": 4,
    "LOCAL_ASSEMBLY_AND_MONTAGE": 5,
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA": 5,
    "READY_FOR_FINAL_HUMAN_REVIEW": 6,
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _stage_from_episode(episode) -> str | None:
    for blocker in getattr(episode, "blockers", ()):
        if blocker.startswith("V6_STAGE="):
            return blocker.split("=", 1)[1]
    return None


class _AutopilotWorker(QThread):
    progress_changed = Signal(str, int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    entered = Signal()
    heartbeat = Signal()

    def __init__(self, repo_root: Path, parent=None):
        super().__init__(parent)
        self.repo_root = repo_root

    def run(self) -> None:
        self.entered.emit()
        self.heartbeat.emit()
        # SIRAJ_R9_2_1_QTHREAD_START_PROBE
        try:
            import json as _r92_json
            import os as _r92_os
            import threading as _r92_threading
            from datetime import datetime as _r92_datetime, timezone as _r92_timezone

            _r92_dir = self.repo_root / "projects" / "_series"
            _r92_dir.mkdir(parents=True, exist_ok=True)
            _r92_path = _r92_dir / "production-worker-checkpoints-r9-2-1.jsonl"
            _r92_row = {
                "event_type": "WORKER_RUN_RAW_ENTERED",
                "timestamp_utc": _r92_datetime.now(_r92_timezone.utc).isoformat().replace("+00:00", "Z"),
                "pid": _r92_os.getpid(),
                "thread_ident": _r92_threading.get_ident(),
            }
            with _r92_path.open("a", encoding="utf-8") as _r92_handle:
                _r92_handle.write(_r92_json.dumps(_r92_row, ensure_ascii=False, sort_keys=True) + "\n")
        except Exception:
            pass

        try:
            _r911_inspection = inspect_autopilot(self.repo_root)
            emit_event(
                self.repo_root,
                _r911_inspection.episode_id,
                "WORKER_THREAD_ENTERED",
                stage=_r911_inspection.stage,
                message_ar="دخل خيط Autopilot إلى run() فعليًا",
                operation="QThread worker entered run()",
                status="WORKER_RUNNING",
            )
        except Exception:
            pass
        try:
            try:
                import json as _r92_json
                import os as _r92_os
                import threading as _r92_threading
                from datetime import datetime as _r92_datetime, timezone as _r92_timezone

                _r92_dir = self.repo_root / "projects" / "_series"
                _r92_dir.mkdir(parents=True, exist_ok=True)
                _r92_path = _r92_dir / "production-worker-checkpoints-r9-2-1.jsonl"
                _r92_row = {
                    "event_type": "WORKER_BEFORE_RUN_UNTIL_GATE",
                    "timestamp_utc": _r92_datetime.now(_r92_timezone.utc).isoformat().replace("+00:00", "Z"),
                    "pid": _r92_os.getpid(),
                    "thread_ident": _r92_threading.get_ident(),
                }
                with _r92_path.open("a", encoding="utf-8") as _r92_handle:
                    _r92_handle.write(_r92_json.dumps(_r92_row, ensure_ascii=False, sort_keys=True) + "\n")
            except Exception:
                pass

            result = run_until_gate(
                self.repo_root,
                progress=lambda stage, done, total, action: (
                    self.progress_changed.emit(
                        str(stage),
                        int(done),
                        int(total),
                        str(action),
                    )
                ),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


class _PaidAuthorizationDialog(QDialog):
    def __init__(
        self,
        stage: str,
        phrase: str,
        detail: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.phrase = phrase
        self.setWindowTitle("تفويض الإنتاج — سراج")
        self.setMinimumWidth(680)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("تفويض واحد لدورة الإنتاج")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {COLORS['gold']};"
        )
        root.addWidget(title)

        stage_label = QLabel(
            "المرحلة: " + V6_STAGE_AR.get(stage, stage)
        )
        stage_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        root.addWidget(stage_label)

        detail_label = QLabel(detail)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet(
            f"color: {COLORS['muted']}; line-height: 1.5;"
        )
        root.addWidget(detail_label)

        warning = QLabel(
            "هذا التفويض يغطي العمليات المدفوعة الأولية لبقية الحلقة حتى المراجعة البشرية النهائية. "
            "لن يعيد سراج أي محاولة مدفوعة تلقائيًا؛ الفشل أو النتيجة المجهولة يتطلبان تفويض إعادة محاولة منفصلًا."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            f"color: {COLORS['orange']};"
            "background: #2b1e12; border: 1px solid #7b4c1c;"
            "border-radius: 9px; padding: 10px;"
        )
        root.addWidget(warning)

        prompt = QLabel("اكتب العبارة التالية حرفيًا:")
        root.addWidget(prompt)

        phrase_label = QLabel(phrase)
        phrase_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        phrase_label.setStyleSheet(
            f"color: {COLORS['gold']}; font-weight: 800;"
            "background: #121b24; border: 1px solid #344454;"
            "border-radius: 8px; padding: 10px;"
        )
        root.addWidget(phrase_label)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("عبارة التفويض")
        root.addWidget(self.entry)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("إلغاء")
        cancel.clicked.connect(self.reject)
        self.confirm = QPushButton("تفويض ومتابعة")
        self.confirm.setEnabled(False)
        self.confirm.setStyleSheet(
            f"font-weight: 800; color: #111; background: {COLORS['gold']};"
            "padding: 9px 16px; border-radius: 8px;"
        )
        self.confirm.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(self.confirm)
        root.addLayout(actions)

        self.entry.textChanged.connect(
            lambda value: self.confirm.setEnabled(
                value.strip() == self.phrase
            )
        )




class _EventsLunaWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        episode_id: str,
        message: str,
        parent=None,
    ):
        super().__init__(parent)
        self.repo_root = repo_root
        self.episode_id = episode_id
        self.message = message

    def run(self) -> None:
        try:
            result = discuss_events_with_luna(
                self.repo_root,
                self.episode_id,
                self.message,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


class EventReviewDialogV66(QDialog):
    approved = Signal()

    def __init__(
        self,
        repo_root: Path,
        episode_id: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root
        self.episode_id = episode_id
        self.worker: _EventsLunaWorker | None = None

        self.setWindowTitle("سراج — مراجعة أحداث الحلقة مع Luna")
        self.setMinimumSize(900, 690)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(9)

        title = QLabel("بوابة اعتماد أحداث الحلقة")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {COLORS['gold']};"
        )
        root.addWidget(title)

        info = QLabel(
            "راجع الأحداث التي ستبنى عليها الحلقة. يمكنك مناقشة Luna لتعديل "
            "الترتيب أو الدمج أو الحذف ضمن المصادر المعتمدة. بعد اعتماد الأحداث "
            "يكمل Autopilot جميع المراحل التالية تلقائيًا تحت تفويض الحلقة الواحد."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {COLORS['muted']};")
        root.addWidget(info)

        body = QHBoxLayout()
        self.events_view = QPlainTextEdit()
        self.events_view.setReadOnly(True)
        self.events_view.setPlaceholderText("أحداث الحلقة")
        body.addWidget(self.events_view, 1)

        self.chat_view = QPlainTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setPlaceholderText("نقاشك مع Luna")
        body.addWidget(self.chat_view, 1)
        root.addLayout(body, 1)

        message_row = QHBoxLayout()
        self.message = QLineEdit()
        self.message.setPlaceholderText(
            "مثال: أريد تقديم الحدث الثالث قبل الثاني، هل هذا أدق سرديًا ومصدرًا؟"
        )
        self.send = QPushButton("ناقش مع Luna")
        self.send.clicked.connect(self._send)
        message_row.addWidget(self.message, 1)
        message_row.addWidget(self.send)
        root.addLayout(message_row)

        note = QLabel(
            "نقاش Luna مغطى بتفويض الحلقة الكامل. لا توجد إعادة محاولة آلية لأي طلب مدفوع."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['blue']};")
        root.addWidget(note)

        actions = QHBoxLayout()
        cancel = QPushButton("إغلاق دون اعتماد")
        cancel.clicked.connect(self.reject)
        self.approve = QPushButton("اعتماد الأحداث ومتابعة الإنتاج آليًا")
        self.approve.setStyleSheet(
            f"font-weight: 800; color: #111; background: {COLORS['gold']};"
            "padding: 9px 15px; border-radius: 8px;"
        )
        self.approve.clicked.connect(self._approve)
        actions.addWidget(cancel)
        actions.addStretch(1)
        actions.addWidget(self.approve)
        root.addLayout(actions)

        self._refresh()

    def _format_events(self, plan) -> str:
        rows = []
        for event in plan.get("events") or []:
            if not isinstance(event, dict):
                continue
            order = event.get("order", "—")
            title = str(event.get("title_ar") or "—")
            summary = str(event.get("summary_ar") or "")
            claims = ", ".join(
                str(item)
                for item in (event.get("claim_ids") or [])
            ) or "—"
            rows.append(
                f"{order}. {title}\n"
                f"   {summary}\n"
                f"   الادعاءات: {claims}"
            )
        return "\n\n".join(rows) or "لا توجد أحداث قابلة للعرض."

    def _refresh(self) -> None:
        plan = load_event_plan(
            self.repo_root,
            self.episode_id,
        )
        self.events_view.setPlainText(
            self._format_events(plan)
        )
        entries = conversation_entries(
            self.repo_root,
            self.episode_id,
        )
        lines = []
        for entry in entries:
            human = str(entry.get("human_message_ar") or "")
            luna = str(entry.get("assistant_message_ar") or "")
            if human:
                lines.append("أنت:\n" + human)
            if luna:
                lines.append("Luna:\n" + luna)
        self.chat_view.setPlainText(
            "\n\n".join(lines)
        )
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    def _send(self) -> None:
        text = self.message.text().strip()
        if not text or (
            self.worker is not None
            and self.worker.isRunning()
        ):
            return

        self.send.setEnabled(False)
        self.approve.setEnabled(False)
        self.send.setText("Luna تعمل…")

        worker = _EventsLunaWorker(
            self.repo_root,
            self.episode_id,
            text,
            self,
        )
        self.worker = worker
        worker.succeeded.connect(self._luna_success)
        worker.failed.connect(self._luna_failure)
        worker.finished.connect(self._luna_finished)
        worker.start()

    def _luna_success(self, result) -> None:
        self.message.clear()
        self._refresh()
        QMessageBox.information(
            self,
            "Luna",
            str(
                result.get("assistant_message_ar")
                or "تمت مراجعة الأحداث."
            ),
        )

    def _luna_failure(self, error: str) -> None:
        QMessageBox.critical(
            self,
            "توقف نقاش Luna",
            error
            + "\n\nلم تتم أي إعادة محاولة تلقائية.",
        )

    def _luna_finished(self) -> None:
        self.send.setEnabled(True)
        self.approve.setEnabled(True)
        self.send.setText("ناقش مع Luna")

    def _approve(self) -> None:
        approve_events(
            self.repo_root,
            self.episode_id,
        )
        self.approved.emit()
        self.accept()


class LiveProductionMonitorV66(QDialog):
    """R9 monitor: displays execution events emitted by the worker itself."""
    def __init__(
        self,
        repo_root: Path,
        parent=None,
        resume_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = Path(repo_root).resolve()
        self._resume_callback = resume_callback
        self.runtime_action = "—"
        self._worker_active = False
        self._current_episode_id = ""
        self._current_file = ""
        self._last_file = ""

        self.setWindowTitle("سراج — الإنتاج المباشر R9")
        self.setMinimumSize(720, 620)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(8)

        title = QLabel("شاشة الإنتاج المباشر — Telemetry فعلية")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {COLORS['gold']};"
        )
        root.addWidget(title)

        self.episode = QLabel("—")
        self.stage = QLabel("—")
        self.operation = QLabel("لا توجد telemetry تنفيذية بعد")
        self.operation.setWordWrap(True)
        self.status = QLabel("—")
        self.updated = QLabel("—")
        self.provider_model = QLabel("—")
        self.request_info = QLabel("—")
        self.cost_info = QLabel("—")

        grid = QGridLayout()
        rows = (
            ("الحلقة:", self.episode),
            ("المرحلة:", self.stage),
            ("العملية الدقيقة الآن:", self.operation),
            ("الحالة:", self.status),
            ("آخر تحديث تنفيذي:", self.updated),
            ("المزوّد / النموذج:", self.provider_model),
            ("الطلب / المهمة:", self.request_info),
            ("الكلفة المسجلة:", self.cost_info),
        )
        for row, (caption, widget) in enumerate(rows):
            grid.addWidget(QLabel(caption), row, 1)
            grid.addWidget(widget, row, 0)
        grid.setColumnStretch(0, 1)
        root.addLayout(grid)

        self.subprogress = QProgressBar()
        self.subprogress.setRange(0, 1)
        root.addWidget(self.subprogress)
        self.progress_text = QLabel("لا يوجد عداد داخلي فعلي لهذه العملية")
        self.progress_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.progress_text)

        self.input_path = QLineEdit()
        self.input_path.setReadOnly(True)
        self.output_path = QLineEdit()
        self.output_path.setReadOnly(True)
        self.last_path = QLineEdit()
        self.last_path.setReadOnly(True)
        paths = QGridLayout()
        paths.addWidget(QLabel("ملف الإدخال الحالي:"), 0, 1)
        paths.addWidget(self.input_path, 0, 0)
        paths.addWidget(QLabel("ملف الإخراج الحالي:"), 1, 1)
        paths.addWidget(self.output_path, 1, 0)
        paths.addWidget(QLabel("آخر ملف مكتمل:"), 2, 1)
        paths.addWidget(self.last_path, 2, 0)
        paths.setColumnStretch(0, 1)
        root.addLayout(paths)

        recent_title = QLabel("آخر النشاطات التنفيذية")
        recent_title.setStyleSheet("font-weight: 700;")
        root.addWidget(recent_title)
        self.recent = QPlainTextEdit()
        self.recent.setReadOnly(True)
        self.recent.setMaximumBlockCount(120)
        root.addWidget(self.recent, 1)

        actions = QHBoxLayout()
        self.resume_autopilot = QPushButton("استئناف Autopilot من شاشة المراقبة")
        self.resume_autopilot.clicked.connect(self._resume_autopilot_from_monitor)
        actions.addWidget(self.resume_autopilot)
        open_current = QPushButton("فتح الملف الحالي")
        open_current.clicked.connect(self._open_current)
        open_last = QPushButton("فتح آخر ملف")
        open_last.clicked.connect(self._open_last)
        open_stage = QPushButton("فتح مجلد المرحلة")
        open_stage.clicked.connect(self._open_stage_folder)
        open_log = QPushButton("فتح سجل Telemetry")
        open_log.clicked.connect(self._open_log)
        close = QPushButton("إخفاء")
        close.clicked.connect(self.hide)
        for button in (open_current, open_last, open_stage, open_log, close):
            actions.addWidget(button)
        root.addLayout(actions)

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh_state)
        self.timer.start()
        self.refresh_state()

    def set_runtime_action(
        self, stage: str, action: str, done: int | None = None,
        total: int | None = None,
    ) -> None:
        # Kept only for compatibility with the existing command center. R9 does
        # not present this inferred string as the exact current operation.
        self.runtime_action = f"{stage}:{action}"
        self.refresh_state()

    def set_runtime_error(self, error: str) -> None:
        self._runtime_error = str(error)
        self.status.setText("FAILED")
        self.operation.setText(str(error))

    def _resolve_path(self, value: str) -> Path | None:
        text = str(value or "").strip()
        if not text:
            return None
        p = Path(text)
        if not p.is_absolute():
            p = self.repo_root / p
        return p

    def _open(self, value: str) -> None:
        p = self._resolve_path(value)
        if p is None or not p.exists():
            QMessageBox.information(self, "سراج", "المسار غير موجود حاليًا.")
            return
        try:
            os.startfile(str(p))
        except Exception as exc:
            QMessageBox.warning(self, "سراج", "تعذر فتح المسار: " + str(exc))

    def _open_current(self) -> None:
        self._open(self._current_file)

    def _open_last(self) -> None:
        self._open(self._last_file)

    def _open_stage_folder(self) -> None:
        if not self._current_episode_id:
            return
        self._open(str(self.repo_root / "projects" / self._current_episode_id / "orchestration"))

    def _open_log(self) -> None:
        if not self._current_episode_id:
            return
        _, events_path = live_paths(self.repo_root, self._current_episode_id)
        self._open(str(events_path))

    def _resume_autopilot_from_monitor(self) -> None:
        if getattr(self, "_worker_active", False):
            return
        if self._resume_callback is not None:
            self._resume_callback()
            return
        parent = self.parent()
        action = getattr(parent, "primary_action", None)
        if not callable(action):
            QMessageBox.warning(
                self,
                "سراج",
                "تعذر الوصول إلى أمر تشغيل Autopilot من شاشة المراقبة.",
            )
            return
        action()
    
    # SIRAJ_R9_3_LIVE_MONITOR_WORKER_STATE_FIX
    def set_worker_active(self, active: bool) -> None:
        active = bool(active)
        self._worker_active = active
        self.resume_autopilot.setEnabled(not active)

        if active:
            self.status.setText("WORKER_STARTING")
            self.operation.setText("بدء خيط Autopilot…")
        else:
            # The 500 ms telemetry refresh remains the source of truth for
            # stage/operation/status after the worker finishes or stops.
            self.refresh_state()

    def closeEvent(self, event) -> None:
        if getattr(self, "_worker_active", False):
            event.ignore()
            self.hide()
            return
        event.accept()

    def refresh_state(self) -> None:
        try:
            inspection = inspect_autopilot(self.repo_root)
        except Exception as exc:
            self.status.setText("تعذر قراءة حالة Autopilot: " + str(exc))
            return

        ep_id = inspection.episode_id
        self._current_episode_id = ep_id
        self.episode.setText(ep_id)
        self.stage.setText(V6_STAGE_AR.get(inspection.stage, inspection.stage))

        state = read_live_state(self.repo_root, ep_id)
        if not state:
            self.operation.setText("لا توجد telemetry تنفيذية فعلية لهذه الحلقة بعد.")
            self.status.setText("Autopilot متوقف/جاهز — لا أدّعي وجود عملية داخلية جارية")
            self.updated.setText("—")
            self.provider_model.setText("—")
            self.request_info.setText("—")
            self.cost_info.setText("—")
            self.input_path.clear(); self.output_path.clear(); self.last_path.clear()
            self.recent.clear()
            self.subprogress.setRange(0, 1); self.subprogress.setValue(0)
            self.progress_text.setText("لا يوجد عداد داخلي فعلي لهذه العملية")
            return

        stage = str(state.get("stage") or inspection.stage)
        self.stage.setText(V6_STAGE_AR.get(stage, stage))
        self.operation.setText(str(state.get("operation") or state.get("message_ar") or "—"))
        self.status.setText(str(state.get("status") or state.get("last_event_type") or "—"))
        self.updated.setText(str(state.get("updated_at_utc") or "—"))
        provider = str(state.get("provider") or "—")
        model = str(state.get("model") or "—")
        self.provider_model.setText(provider + " / " + model)
        rq = state.get("request_current"); rt = state.get("request_total")
        task_uuid = str(state.get("task_uuid") or "—")
        self.request_info.setText(
            (f"{rq} / {rt}" if rq is not None and rt is not None else "—")
            + " • UUID: " + task_uuid
        )
        expected = state.get("expected_cost_usd")
        actual = state.get("actual_cost_usd")
        bits = []
        if expected is not None: bits.append(f"متوقع ${float(expected):.6f}")
        if actual is not None: bits.append(f"فعلي ${float(actual):.6f}")
        self.cost_info.setText(" • ".join(bits) if bits else "—")

        inp = str(state.get("input_path") or "")
        out = str(state.get("output_path") or "")
        last = str(state.get("last_completed_file") or "")
        self.input_path.setText(inp); self.output_path.setText(out); self.last_path.setText(last)
        self._current_file = out or inp
        self._last_file = last

        pc = state.get("progress_current")
        pt = state.get("progress_total")
        if isinstance(pc, (int, float)) and isinstance(pt, (int, float)) and pt > 0:
            self.subprogress.setRange(0, int(pt))
            self.subprogress.setValue(min(int(pt), int(pc)))
            pct = 100.0 * float(pc) / float(pt)
            self.progress_text.setText(f"{pc} / {pt} • {pct:.1f}%")
        elif rq is not None and rt is not None and int(rt) > 0:
            self.subprogress.setRange(0, int(rt))
            self.subprogress.setValue(min(int(rt), int(rq)))
            self.progress_text.setText(f"طلب {rq} / {rt}")
        else:
            self.subprogress.setRange(0, 0)
            self.progress_text.setText("العملية جارية — لا يوجد ETA مصطنع")

        lines = []
        for row in recent_events(self.repo_root, ep_id, 14):
            when = str(row.get("timestamp_utc") or "").replace("T", " ").replace("Z", "")
            msg = str(row.get("message_ar") or row.get("operation") or row.get("event_type") or "")
            et = str(row.get("event_type") or "")
            lines.append(f"{when}  [{et}]  {msg}")
        self.recent.setPlainText("\n".join(lines))
        bar = self.recent.verticalScrollBar()
        bar.setValue(bar.maximum())

class V6CommandCenter(Panel):
    refresh_requested = Signal()
    log_message = Signal(str)

    _PHASES = (
        ("بحث", 0),
        ("قصة", 1),
        ("صوت", 2),
        ("ستوريبورد", 3),
        ("وسائط", 4),
        ("مونتاج", 5),
        ("مراجعة", 6),
    )

    def __init__(
        self,
        repo_root: Path,
        parent=None,
        *,
        primary_action_callback: Callable[[], None] | None = None,
        canonical_state_reader: Callable[[], Any | None] | None = None,
    ) -> None:
        super().__init__(
            object_name="v6OriginalDashboardCommandCenter",
            parent=parent,
        )
        self.repo_root = repo_root.resolve()
        self._primary_action_callback = primary_action_callback
        self._canonical_state_reader = canonical_state_reader
        self.worker: _AutopilotWorker | None = None
        self.worker_lifecycle = WorkerLifecycle()
        self._restart_after_finish = False
        self.setMinimumHeight(204)
        self.setStyleSheet(
            "QFrame#v6OriginalDashboardCommandCenter {"
            "background: #0d1721;"
            "border: 1px solid #33485b;"
            "border-radius: 12px;"
            "}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 11, 16, 11)
        root.setSpacing(8)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Autopilot V6 — التحكم التنفيذي")
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 800; color: {COLORS['gold']};"
        )
        subtitle = QLabel(
            "المرحلة الفعلية للحلقة النشطة، مع التقدم وبوابات الدفع والمراجعة."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {COLORS['muted']};")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)

        self.gate_pill = StatusPill("جارٍ الفحص…", "muted")
        self.gate_pill.setMaximumWidth(260)
        top.addWidget(self.gate_pill)
        root.addLayout(top)

        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(10)
        status_grid.setVerticalSpacing(5)

        self.episode_value = QLabel("—")
        self.stage_value = QLabel("—")
        self.provider_value = QLabel("—")
        self.scope_value = QLabel("—")
        self.authority_value = QLabel("—")
        self.gates_value = QLabel("—")
        for label in (
            self.episode_value,
            self.stage_value,
            self.provider_value,
            self.scope_value,
            self.authority_value,
            self.gates_value,
        ):
            label.setStyleSheet("font-weight: 700;")
            label.setWordWrap(True)

        self.episode_value.setToolTip("—")

        status_grid.addWidget(QLabel("الحلقة:"), 0, 3)
        status_grid.addWidget(self.episode_value, 0, 2)
        status_grid.addWidget(QLabel("المرحلة:"), 0, 1)
        status_grid.addWidget(self.stage_value, 0, 0)
        status_grid.addWidget(QLabel("المزوّد / النموذج:"), 1, 3)
        status_grid.addWidget(self.provider_value, 1, 2)
        status_grid.addWidget(QLabel("الحالة التنفيذية:"), 1, 1)
        status_grid.addWidget(self.scope_value, 1, 0)
        status_grid.addWidget(QLabel("Authority:"), 2, 3)
        status_grid.addWidget(self.authority_value, 2, 2)
        status_grid.addWidget(QLabel("Previous gates:"), 2, 1)
        status_grid.addWidget(self.gates_value, 2, 0)
        status_grid.setColumnStretch(0, 2)
        status_grid.setColumnStretch(2, 2)
        root.addLayout(status_grid)

        metrics = QHBoxLayout()
        metrics.setSpacing(7)
        self.request_metric = self._metric_chip("الطلبات", "—")
        self.character_metric = self._metric_chip("الأحرف", "—")
        self.completed_metric = self._metric_chip("المكتمل", "0")
        self.percent_metric = self._metric_chip("التقدم", "0%")
        for widget in (
            self.request_metric,
            self.character_metric,
            self.completed_metric,
            self.percent_metric,
        ):
            metrics.addWidget(widget, 1)
        root.addLayout(metrics)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, len(STAGES))
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(9)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: #13202b; border: 0; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {COLORS['gold']}; border-radius: 4px; }}"
        )
        self.progress_text = QLabel("0 / 0 • 0%")
        self.progress_text.setStyleSheet(f"color: {COLORS['muted']};")
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_text)
        root.addLayout(progress_row)

        phase_row = QHBoxLayout()
        phase_row.setSpacing(5)
        self.phase_labels: list[QLabel] = []
        for caption, _ in self._PHASES:
            label = QLabel(caption)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(25)
            self.phase_labels.append(label)
            phase_row.addWidget(label, 1)
        root.addLayout(phase_row)

        policies = QHBoxLayout()
        policies.setSpacing(6)
        for text in (
            "True video timeline 50%–75%",
            "Directorial optimization (not a quota)",
            "منع التكرار",
            "النطق الكامل",
            "لا إعادة دفع تلقائية",
        ):
            chip = QLabel(text)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setStyleSheet(
                "color: #a9c7d8; background: #102431;"
                "border: 1px solid #24485d; border-radius: 7px;"
                "padding: 4px 7px; font-size: 10px;"
            )
            policies.addWidget(chip, 1)
        root.addLayout(policies)

        self.live_monitor = LiveProductionMonitorV66(
            self.repo_root,
            self,
            resume_callback=primary_action_callback,
        )

        actions = QHBoxLayout()
        self.primary = QPushButton("ابدأ / استأنف Autopilot")
        self.primary.setMinimumHeight(42)
        self.primary.setStyleSheet(
            f"font-size: 13px; font-weight: 800; color: #111;"
            f"background: {COLORS['gold']}; border-radius: 8px; padding: 8px 14px;"
        )
        self.primary.clicked.connect(self._handle_primary_click)
        refresh = QPushButton("تحديث الحالة")
        refresh.clicked.connect(self.refresh_state)
        live = QPushButton("شاشة الإنتاج المباشر")
        live.clicked.connect(self.live_monitor.show)
        actions.addWidget(self.primary, 2)
        actions.addWidget(live, 1)
        actions.addWidget(refresh, 1)
        root.addLayout(actions)

        self.refresh_state()

    def _handle_primary_click(self) -> None:
        """Route the supported dashboard action through its injected boundary."""

        if self._primary_action_callback is not None:
            self._primary_action_callback()
            return
        # Historical consumers of V6CommandCenter may still use the legacy
        # command center directly.  The supported full desktop launcher always
        # supplies ``primary_action_callback`` and therefore never reaches this
        # branch.
        self.primary_action()

    def _metric_chip(self, caption: str, value: str) -> QLabel:
        label = QLabel(f"{caption}: {value}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "color: #d3e0e8; background: #111f2a;"
            "border: 1px solid #2b4152; border-radius: 7px;"
            "padding: 5px 7px; font-size: 10px; font-weight: 700;"
        )
        return label

    def _set_metric(self, label: QLabel, caption: str, value: object) -> None:
        label.setText(f"{caption}: {value}")

    def _scope_detail(self, inspection) -> tuple[str, str]:
        ep = self.repo_root / "projects" / inspection.episode_id

        if inspection.stage == EVENTS_REVIEW_STAGE:
            return (
                "HUMAN + LUNA / Events Review V6.6",
                "راجع الأحداث وناقش Luna ثم اعتمدها؛ بعدها يكمل الإنتاج تلقائيًا.",
            )

        if inspection.stage == "FINAL_TTS":
            return (
                "ELEVENLABS / eleven_multilingual_v2",
                (
                    "بانتظار التفويض الصريح"
                    if inspection.paid_stage and not inspection.authorized
                    else "الصوت النهائي جاهز للتنفيذ"
                ),
            )

        if inspection.stage == "PROVIDER_EXECUTION":
            return (
                "RUNWARE / Model Router",
                (
                    "بانتظار تفويض توليد الوسائط"
                    if inspection.paid_stage and not inspection.authorized
                    else "توليد الصور والفيديو قيد التنفيذ"
                ),
            )

        if inspection.stage in {
            "AUDIO_TIMESTAMPS_AND_BEATS",
            "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
            "MEDIA_COST_PREFLIGHT",
            "LOCAL_ASSEMBLY_AND_MONTAGE",
        }:
            return (
                "LOCAL / Deterministic V6",
                "عملية محلية — لا تكلفة مزود",
            )

        if inspection.stage == "READY_FOR_FINAL_HUMAN_REVIEW":
            return (
                "HUMAN",
                "المشاهدة البشرية النهائية — النشر يدوي",
            )

        try:
            from src.application.siraj_luna_upstream_transport_v6_3 import (
                resolve_luna_model,
            )
            model = resolve_luna_model()
        except Exception:
            model = "Luna"
        return (
            "OPENAI / " + model,
            (
                "بانتظار تفويض Luna"
                if inspection.paid_stage and not inspection.authorized
                else "Luna جاهزة للتنفيذ"
            ),
        )

    def _stage_metrics(self, inspection) -> tuple[str, str]:
        ep = self.repo_root / "projects" / inspection.episode_id

        if inspection.stage == "FINAL_TTS":
            for path in (
                ep / "orchestration/final-tts-queue-v5-4-3.json",
                ep / "orchestration/final-tts-queue-v6-3-2.json",
            ):
                payload = _read_json(path)
                if not payload:
                    continue
                requests = payload.get("planned_provider_requests")
                items = payload.get("items")
                if requests is None and isinstance(items, list):
                    requests = len(items)
                chars = payload.get("total_character_count_unicode")
                return (
                    str(requests if requests is not None else "—"),
                    f"{int(chars):,}" if isinstance(chars, (int, float)) else "—",
                )

        if inspection.stage == "PROVIDER_EXECUTION":
            queue = _read_json(
                ep / "orchestration/media-production-queue-v6-2-1.json"
            )
            if queue and isinstance(queue.get("items"), list):
                return (str(len(queue["items"])), "—")

        return ("—", "—")

    def _episode_title(self, snapshot, inspection) -> str:
        if snapshot is not None:
            active = getattr(snapshot, "active_episode", None)
            if active is not None and active.episode_id == inspection.episode_id:
                return active.title_ar
        if inspection.episode_id == "episode-002-adam-temptation-fall-repentance":
            return "من الوسوسة إلى التوبة"
        return inspection.episode_id

    def _update_phase_strip(self, stage: str) -> None:
        active = MACRO_STAGE_INDEX.get(stage, 0)
        for index, label in enumerate(self.phase_labels):
            if index < active:
                label.setStyleSheet(
                    f"color: {COLORS['green']}; background: #10261e;"
                    "border: 1px solid #24523c; border-radius: 6px;"
                    "padding: 3px 5px; font-size: 10px; font-weight: 700;"
                )
            elif index == active:
                label.setStyleSheet(
                    f"color: #111; background: {COLORS['gold']};"
                    "border: 1px solid #d49a24; border-radius: 6px;"
                    "padding: 3px 5px; font-size: 10px; font-weight: 800;"
                )
            else:
                label.setStyleSheet(
                    "color: #718799; background: #101923;"
                    "border: 1px solid #233342; border-radius: 6px;"
                    "padding: 3px 5px; font-size: 10px;"
                )

    def _refresh_canonical_state(self, state: Any, snapshot=None) -> None:
        """Render ledger-backed state without consulting V6 projections."""

        episode_id = str(state.episode_id)
        stage = str(state.current_stage)
        title = self._episode_title(snapshot, state)
        self.episode_value.setText(title)
        self.episode_value.setToolTip(episode_id)
        self.stage_value.setText(V6_STAGE_AR.get(stage, stage))
        self.provider_value.setText(
            "RUNWARE / persisted canonical preflight"
            if stage == "PROVIDER_EXECUTION"
            else "LOCAL / Canonical preflight"
        )
        self.scope_value.setText("PAUSED / AWAITING HUMAN RESUME")
        self.authority_value.setText(
            "episode-transition-ledger-v1.jsonl | "
            f"duration={float(state.duration_seconds):.3f}s | "
            f"shots={int(state.shot_count)}"
        )
        self.gates_value.setText(
            f"ALIGNMENT={state.alignment_gate} | "
            f"DUPLICATE={state.duplicate_gate} | "
            f"DISCONTINUITIES={int(state.timeline_discontinuities)}"
        )

        done = len(tuple(state.completed_stages))
        total = len(BASE_STAGE_ORDER)
        percent = round(100 * done / max(1, total), 1)
        preflight = None
        if stage == "PROVIDER_EXECUTION":
            try:
                preflight = read_persisted_media_cost_preflight(
                    self.repo_root,
                    state.episode_id,
                )
            except (MediaCostPreflightError, OSError, ValueError):
                # A missing or mismatched result must never fall back to a
                # legacy queue-derived count or cost.
                preflight = None
        if preflight is not None:
            planned = preflight.summary.get("planned_provider_requests")
            if (
                preflight.pricing_status == "COMPLETE"
                and preflight.estimated_total_cost_usd is not None
            ):
                cost = f"${preflight.estimated_total_cost_usd:.6f}"
            else:
                cost = "UNKNOWN / UNPRICED"
            self._set_metric(
                self.request_metric,
                "الطلبات",
                planned if planned is not None else "UNKNOWN",
            )
            self._set_metric(self.character_metric, "الأجرة", cost)
        else:
            self._set_metric(self.request_metric, "الطلبات", "—")
            self._set_metric(self.character_metric, "الأجرة", "—")
        self._set_metric(self.completed_metric, "المكتمل", f"{done}/{total}")
        self._set_metric(self.percent_metric, "التقدم", f"{percent}%")
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress_text.setText(f"{done} / {total} • {percent}%")
        self._update_phase_strip(stage)

        if stage == "PROVIDER_EXECUTION":
            if preflight is None:
                gate_text = "MEDIA PREFLIGHT REVIEW REQUIRED"
                self.scope_value.setText("PAUSED / AWAITING HUMAN RESUME")
            elif preflight.production_authorization == "VALID":
                gate_text = "MEDIA PREFLIGHT REVIEW / MASTER AUTH VALID"
                self.scope_value.setText("PAUSED / AWAITING HUMAN RESUME")
            elif preflight.production_authorization == "ACTIVE_BUT_UNBOUND_REACK_REQUIRED":
                gate_text = "MEDIA PREFLIGHT REVIEW / COST ENVELOPE RE-ACK REQUIRED"
                self.scope_value.setText("PAUSED / AWAITING HUMAN COST ENVELOPE RE-ACK")
            elif preflight.production_authorization == "VALID_BOUND_TO_CURRENT_COST_ENVELOPE":
                gate_text = "MEDIA PREFLIGHT REVIEW / COST ENVELOPE BOUND"
                self.scope_value.setText("PAUSED / AWAITING HUMAN RESUME")
            else:
                gate_text = "MEDIA PREFLIGHT REVIEW / HUMAN AUTHORIZATION REQUIRED"
                self.scope_value.setText("PAUSED / AWAITING HUMAN AUTHORIZATION")
            self.gate_pill.set_text(gate_text)
            self.primary.setText(
                "Resume current stage (Desktop UI)"
                if preflight is not None
                and preflight.production_authorization
                == "VALID_BOUND_TO_CURRENT_COST_ENVELOPE"
                else "Review media preflight"
            )
            self.primary.setEnabled(preflight is not None)
        else:
            self.gate_pill.set_text("PAUSED / AWAITING HUMAN RESUME")
            self.primary.setText("Resume current stage (Desktop UI)")
            self.primary.setEnabled(
                stage in {"MEDIA_COST_PREFLIGHT", "LOCAL_ASSEMBLY_AND_MONTAGE", "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA"}
            )

    def refresh_state(self, snapshot=None) -> None:
        if self._canonical_state_reader is not None:
            try:
                canonical = self._canonical_state_reader()
            except Exception as exc:
                self.gate_pill.set_text("AUTHORITATIVE STATE UNAVAILABLE")
                self.stage_value.setText(str(exc))
                self.authority_value.setText("episode-transition-ledger-v1.jsonl")
                self.gates_value.setText("FAIL_CLOSED")
                self.primary.setEnabled(False)
                return
            if canonical is not None:
                self._refresh_canonical_state(canonical, snapshot)
                return

        try:
            inspection = inspect_autopilot(self.repo_root)
        except Exception as exc:
            self.gate_pill.set_text("تعذر قراءة V6")
            self.stage_value.setText(str(exc))
            self.primary.setEnabled(False)
            return

        if snapshot is None:
            try:
                snapshot = build_v6_dashboard_snapshot(self.repo_root)
            except Exception:
                snapshot = None

        provider, scope = self._scope_detail(inspection)
        title = self._episode_title(snapshot, inspection)
        self.episode_value.setText(title)
        self.episode_value.setToolTip(inspection.episode_id)
        self.stage_value.setText(
            V6_STAGE_AR.get(inspection.stage, inspection.stage)
        )
        self.provider_value.setText(provider)
        self.scope_value.setText(scope)

        request_count, chars = self._stage_metrics(inspection)
        done = len(inspection.completed_stages)
        total = len(STAGES)
        percent = round(100 * done / max(1, total), 1)

        self._set_metric(self.request_metric, "الطلبات", request_count)
        self._set_metric(self.character_metric, "الأحرف", chars)
        self._set_metric(self.completed_metric, "المكتمل", f"{done}/{total}")
        self._set_metric(self.percent_metric, "التقدم", f"{percent}%")

        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress_text.setText(f"{done} / {total} • {percent}%")
        self._update_phase_strip(inspection.stage)

        if inspection.terminal:
            self.gate_pill.set_text("جاهزة للمراجعة البشرية")
            self.primary.setText("فتح المراجعة النهائية")
            self.primary.setEnabled(False)
        elif inspection.stage == EVENTS_REVIEW_STAGE:
            self.gate_pill.set_text("اعتماد الأحداث مطلوب")
            self.primary.setText("مراجعة أحداث الحلقة مع Luna")
            self.primary.setEnabled(True)
        elif inspection.paid_stage and not inspection.authorized:
            if "RETRY" in inspection.action:
                self.gate_pill.set_text("تفويض إعادة محاولة مطلوب")
                self.primary.setText("تفويض إعادة المحاولة المدفوعة")
            else:
                self.gate_pill.set_text("تفويض الحلقة الكامل مطلوب")
                self.primary.setText("تفويض الإنتاج الكامل للحلقة")
            self.primary.setEnabled(True)
        else:
            self.gate_pill.set_text("مغطى بتفويض الحلقة / جاهز")
            self.primary.setText("استئناف Autopilot")
            self.primary.setEnabled(True)

    def _authorization_detail(self, inspection) -> str:
        provider, scope = self._scope_detail(inspection)
        requests, chars = self._stage_metrics(inspection)
        metrics = ""
        if requests != "—":
            metrics += f"\nالطلبات المخططة: {requests}"
        if chars != "—":
            metrics += f"\nالأحرف: {chars}"
        if "RETRY" in inspection.action:
            return (
                f"{provider}\n{scope}{metrics}\n\n"
                "هذا تفويض استثنائي لإعادة محاولة المرحلة الحالية فقط. "
                "لا توجد إعادة محاولة تلقائية."
            )
        return (
            f"{provider}\n{scope}{metrics}\n\n"
            "تفويض واحد يغطي العمليات المدفوعة الأولية لبقية الحلقة حتى "
            "READY_FOR_FINAL_HUMAN_REVIEW. المراحل المكتملة لن تُعاد، "
            "والنشر يبقى يدويًا. أي محاولة مدفوعة فاشلة/مجهولة لا تُعاد "
            "إلا بتفويض إعادة محاولة منفصل."
        )

    def primary_action(self) -> None:
        if self._primary_action_callback is not None:
            # The supported full dashboard injects the canonical Desktop
            # controller here.  This guard also protects programmatic calls to
            # the historical method from bypassing that boundary.
            self._primary_action_callback()
            return
        try:
            _r911_inspection = inspect_autopilot(self.repo_root)
            emit_event(
                self.repo_root,
                _r911_inspection.episode_id,
                "RESUME_ACTION_RECEIVED",
                stage=_r911_inspection.stage,
                message_ar="استقبلت الواجهة أمر بدء/استئناف Autopilot",
                operation="فحص تفويض V6.6 ثم تجهيز Worker",
                status="START_REQUESTED",
                details={
                    "effective_action": _r911_inspection.action,
                    "effective_authorized": bool(_r911_inspection.authorized),
                    "paid_stage": bool(_r911_inspection.paid_stage),
                },
            )
        except Exception:
            pass
        if self.worker is not None and self.worker.isRunning():
            return

        inspection = inspect_autopilot(self.repo_root)
        if inspection.terminal:
            QMessageBox.information(
                self,
                "سراج",
                "الحلقة جاهزة للمراجعة البشرية النهائية.",
            )
            return

        if inspection.stage == EVENTS_REVIEW_STAGE:
            dialog = EventReviewDialogV66(
                self.repo_root,
                inspection.episode_id,
                self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh_state()
                self._restart_after_finish = True
            return

        if inspection.paid_stage and not inspection.authorized:
            stage, phrase = authorization_phrase_for(self.repo_root)
            dialog = _PaidAuthorizationDialog(
                stage,
                phrase,
                self._authorization_detail(inspection),
                self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                authorize_current_stage(
                    self.repo_root,
                    phrase,
                )
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "فشل التفويض",
                    str(exc),
                )
                self.refresh_state()
                return
            self.log_message.emit("V6_AUTHORIZED " + stage)

        self._launch_autopilot_worker()

    def _launch_autopilot_worker(self) -> None:
        self.worker_lifecycle = self.worker_lifecycle.start_requested()
        try:
            _r911_inspection = inspect_autopilot(self.repo_root)
            emit_event(
                self.repo_root,
                _r911_inspection.episode_id,
                "WORKER_LAUNCH_REQUESTED",
                stage=_r911_inspection.stage,
                message_ar="طلبت الواجهة إنشاء وتشغيل Worker الخاص بـAutopilot",
                operation="إنشاء QThread واستدعاء start()",
                status="WORKER_STARTING",
                details={
                    "effective_action": _r911_inspection.action,
                    "effective_authorized": bool(_r911_inspection.authorized),
                },
            )
        except Exception:
            pass
        self.primary.setEnabled(False)
        self.gate_pill.set_text("Autopilot يعمل…")
        self.live_monitor.show()
        self.live_monitor.raise_()
        self.live_monitor.set_worker_active(True)
        validate_monitor_contract(self.live_monitor)

        worker = _AutopilotWorker(
            self.repo_root,
            self,
        )
        self.worker = worker
        worker.progress_changed.connect(self._on_progress)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.entered.connect(self._on_worker_entered)
        worker.heartbeat.connect(self._on_worker_heartbeat)
        worker.finished.connect(self._on_finished)
        worker.start()

        QTimer.singleShot(30_000, self._worker_watchdog_check)

        try:
            _r92_inspection = inspect_autopilot(self.repo_root)
            emit_event(
                self.repo_root,
                _r92_inspection.episode_id,
                "WORKER_START_RETURNED",
                stage=_r92_inspection.stage,
                message_ar="عاد QThread.start() إلى الواجهة",
                operation="فحص حالة Worker مباشرة بعد start()",
                status="WORKER_START_RETURNED",
                details={
                    "is_running": bool(worker.isRunning()),
                    "is_finished": bool(worker.isFinished()),
                    "worker_object_id": int(id(worker)),
                },
            )
        except Exception:
            pass

        def _r92_probe_worker_state(label: str) -> None:
            try:
                _r92_inspection = inspect_autopilot(self.repo_root)
                emit_event(
                    self.repo_root,
                    _r92_inspection.episode_id,
                    f"WORKER_STATE_PROBE_{label}",
                    stage=_r92_inspection.stage,
                    message_ar=f"فحص حالة Worker بعد {label}",
                    operation="QThread state probe",
                    status="WORKER_STATE_PROBE",
                    details={
                        "is_running": bool(worker.isRunning()),
                        "is_finished": bool(worker.isFinished()),
                        "worker_object_id": int(id(worker)),
                    },
                )
            except Exception:
                pass

        QTimer.singleShot(250, lambda: _r92_probe_worker_state("250MS"))
        QTimer.singleShot(2000, lambda: _r92_probe_worker_state("2000MS"))

    def _on_progress(
        self,
        stage: str,
        done: int,
        total: int,
        action: str,
    ) -> None:
        percent = round(100 * done / max(1, total), 1)
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress_text.setText(
            f"{done} / {total} • {percent}%"
        )
        self._set_metric(
            self.completed_metric,
            "المكتمل",
            f"{done}/{total}",
        )
        self._set_metric(
            self.percent_metric,
            "التقدم",
            f"{percent}%",
        )
        self.stage_value.setText(
            V6_STAGE_AR.get(stage, stage)
        )
        self._update_phase_strip(stage)
        self.live_monitor.set_runtime_action(
            stage,
            action,
            done,
            total,
        )
        self.log_message.emit(
            f"V6 {stage} {action}"
        )

    def _on_success(self, result) -> None:
        self.worker_lifecycle = self.worker_lifecycle.terminal()
        self.log_message.emit(
            "V6_RESULT "
            + result.status
            + " "
            + result.stage
        )
        if result.status == "EVENTS_REVIEW_REQUIRED":
            dialog = EventReviewDialogV66(
                self.repo_root,
                result.episode_id,
                self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh_state()
                self._launch_autopilot_worker()
            return
        if result.status in {
            "FULL_EPISODE_AUTHORIZATION_REQUIRED",
            "PAID_RETRY_AUTHORIZATION_REQUIRED",
        }:
            self.refresh_state()
            return
        elif result.status == "READY_FOR_FINAL_HUMAN_REVIEW":
            QMessageBox.information(
                self,
                "اكتمل الإنتاج الآلي",
                "الحلقة جاهزة للمشاهدة والمراجعة البشرية النهائية. "
                "لم يتم النشر تلقائيًا.",
            )

    def _on_failure(self, error: str) -> None:
        self.worker_lifecycle = self.worker_lifecycle.terminal(error=error)
        self.live_monitor.set_runtime_error(error)
        self.log_message.emit(
            "V6_STOPPED " + error
        )
        QMessageBox.critical(
            self,
            "توقف Autopilot",
            error,
        )

    def _on_finished(self) -> None:
        if self.worker_lifecycle.state in {WorkerState.STARTING, WorkerState.RUNNING}:
            self.worker_lifecycle = self.worker_lifecycle.terminal(
                error="WORKER_FINISHED_WITHOUT_TERMINAL_SIGNAL"
            )
        self.worker_lifecycle = self.worker_lifecycle.finished()
        self.live_monitor.set_worker_active(False)
        self.refresh_state()
        self.refresh_requested.emit()
        self.primary.setEnabled(True)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        if self._restart_after_finish:
            self._restart_after_finish = False
            QTimer.singleShot(0, self._launch_autopilot_worker)

    def _on_worker_entered(self) -> None:
        self.worker_lifecycle = self.worker_lifecycle.entered()

    def _on_worker_heartbeat(self) -> None:
        if self.worker_lifecycle.state == WorkerState.RUNNING:
            self.worker_lifecycle = self.worker_lifecycle.heartbeat()

    def _worker_watchdog_check(self) -> None:
        self.worker_lifecycle = self.worker_lifecycle.watchdog(timeout_seconds=30.0)
        if self.worker_lifecycle.state == WorkerState.STALLED:
            self.live_monitor.set_runtime_error("LOCAL_WORKER_HEARTBEAT_TIMEOUT")


def _workflow_set_episode(self, episode) -> None:
    if episode is None:
        states = ["blocked"] * len(self.stage_labels)
    else:
        stage = _stage_from_episode(episode)
        if not stage:
            return self._siraj_v6_original_set_episode(episode)

        active_index = MACRO_STAGE_INDEX.get(stage, 0)
        states = []
        for index in range(len(self.stage_labels)):
            if index < active_index:
                states.append("complete")
            elif index == active_index:
                states.append("active")
            else:
                states.append("waiting")

    for label, state in zip(
        self.stage_labels,
        states,
        strict=True,
    ):
        self._style_stage(label, state)


def _approval_refresh_v6(self, snapshot) -> None:
    active = snapshot.active_episode
    if active is not None:
        canonical_stage = next(
            (
                blocker.split("=", 1)[1]
                for blocker in active.blockers
                if blocker.startswith("V6_STAGE=")
            ),
            None,
        )
        canonical_source = next(
            (
                blocker.split("=", 1)[1]
                for blocker in active.blockers
                if blocker.startswith("AUTHORITATIVE_STATE=")
            ),
            None,
        )
        if canonical_stage and canonical_source:
            root = active.project_path
            ledger = root / "orchestration/episode-transition-ledger-v1.jsonl"
            alignment = root / "orchestration/alignment-gate-promoted-v1.json"
            duplicate = root / "orchestration/prompt-similarity-duplicate-gate-promoted-v1.json"
            rows = [
                (
                    "Authoritative transition ledger",
                    "PASS",
                    ledger if ledger.is_file() else None,
                ),
                (
                    "NARRATION_VISUAL_ALIGNMENT_GATE",
                    "PASS",
                    alignment if alignment.is_file() else None,
                ),
                (
                    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
                    "PASS",
                    duplicate if duplicate.is_file() else None,
                ),
                (
                    "Current production status",
                    "PAUSED / AWAITING HUMAN RESUME",
                    ledger if ledger.is_file() else None,
                ),
            ]
            self.current_directive.setText(
                "Current authoritative stage: "
                + canonical_stage
                + " — source: "
                + canonical_source
                + " — resume: DESKTOP_UI_ONLY"
            )
            self._paths = [path for _, _, path in rows]
            self.table.setRowCount(len(rows))
            for row, (gate, status, path) in enumerate(rows):
                evidence = str(path) if path is not None else "—"
                for column, value in enumerate((gate, status, evidence)):
                    item = QTableWidgetItem(value)
                    if column == 1:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(value)
                    self.table.setItem(row, column, item)
            if rows:
                self.table.selectRow(0)
            self.open_evidence_button.setEnabled(
                any(path is not None for path in self._paths)
            )
            return

    from src.application.siraj_autopilot_v6_6 import (
        inspect_autopilot,
    )

    try:
        inspection = inspect_autopilot(snapshot.repo_root)
    except Exception as exc:
        self.current_directive.setText(
            "تعذر قراءة Autopilot V6: " + str(exc)
        )
        self.table.setRowCount(0)
        self._paths = []
        self.open_evidence_button.setEnabled(False)
        return

    if active is None:
        self.current_directive.setText("لا توجد حلقة نشطة.")
        self.table.setRowCount(0)
        self._paths = []
        self.open_evidence_button.setEnabled(False)
        return

    root = active.project_path
    runtime = (
        snapshot.repo_root
        / "projects/_series/siraj-series-autopilot-runtime-v6-4.json"
    )
    policy = (
        snapshot.repo_root
        / "projects/_series/siraj-cinematic-media-mix-policy-v2.json"
    )
    pronunciation = (
        root / "orchestration/pronunciation-audit-v6-3.json"
    )
    if active.episode_id == "episode-002-adam-temptation-fall-repentance":
        pronunciation = (
            root
            / "preproduction/luna-pronunciation-performance-gate-v5-3-4r2.json"
        )

    duplicate = root / "orchestration/prompt-duplicate-gate-v6-4.json"
    ready = (
        root
        / "orchestration/ready-for-final-human-review-v6-4.json"
    )

    auth_path = None
    auth_status = "لا توجد بوابة مدفوعة حاليًا"
    if inspection.paid_stage:
        if inspection.stage == "FINAL_TTS":
            auth_path = (
                root
                / (
                    "orchestration/final-tts-paid-authorization-v5-4-3.json"
                    if active.episode_id
                    == "episode-002-adam-temptation-fall-repentance"
                    else "orchestration/final-tts-paid-authorization-v6-3-2.json"
                )
            )
        elif inspection.stage == "PROVIDER_EXECUTION":
            auth_path = (
                root
                / "orchestration/"
                "media-production-paid-authorization-v6-2-1.json"
            )
        else:
            auth_path = (
                root
                / "orchestration/luna-v6-3/"
                / inspection.stage.lower()
                / "paid-authorization.json"
            )
        auth_status = (
            "معتمدة"
            if inspection.authorized
            else "بانتظار تفويض صريح"
        )

    rows = [
        (
            "Autopilot V6",
            V6_STAGE_AR.get(
                inspection.stage,
                inspection.stage,
            ),
            runtime if runtime.is_file() else None,
        ),
        (
            "التفويض المدفوع الحالي",
            auth_status,
            auth_path if auth_path and auth_path.is_file() else None,
        ),
        (
            "قانون النطق العربي الكامل",
            "PASS" if pronunciation.is_file() else "بانتظار مرحلته",
            pronunciation if pronunciation.is_file() else None,
        ),
        (
            "سياسة الفيديو / الصور",
            "True video timeline 50%–75% — directorially selected",
            policy if policy.is_file() else None,
        ),
        (
            "بوابات منع التكرار",
            "PASS" if duplicate.is_file() else "تُطبق قبل/بعد التوليد",
            duplicate if duplicate.is_file() else None,
        ),
        (
            "المراجعة البشرية النهائية",
            "READY" if ready.is_file() else "لم تصل بعد",
            ready if ready.is_file() else None,
        ),
        (
            "النشر",
            "HUMAN_ONLY — يدوي دائمًا",
            ready if ready.is_file() else None,
        ),
    ]

    self.current_directive.setText(
        "المرحلة المطلوبة الآن: "
        + V6_STAGE_AR.get(
            inspection.stage,
            inspection.stage,
        )
        + " — "
        + (
            "تحتاج تفويضًا مدفوعًا صريحًا."
            if inspection.paid_stage and not inspection.authorized
            else "جاهزة للمتابعة."
        )
    )

    self._paths = [path for _, _, path in rows]
    self.table.setRowCount(len(rows))
    for row, (gate, status, path) in enumerate(rows):
        evidence = str(path) if path is not None else "—"
        for column, value in enumerate((gate, status, evidence)):
            item = QTableWidgetItem(value)
            if column == 1:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )
            item.setToolTip(value)
            self.table.setItem(
                row,
                column,
                item,
            )
    if rows:
        self.table.selectRow(0)
    self.open_evidence_button.setEnabled(
        any(path is not None for path in self._paths)
    )


def _video_publish_refresh_v6(self, snapshot) -> None:
    active = snapshot.active_episode
    if active is None:
        for label in self.labels.values():
            label.setText("لا توجد حلقة نشطة")
        self._final_video = None
        self._publish_dir = None
        return

    root = active.project_path
    final = (
        root
        / "deliverables/autopilot-v6-2-1/"
        "episode-master-autopilot-v6-2-1.mp4"
    )
    if not final.is_file() and active.final_video_path is not None:
        final = active.final_video_path

    qa = (
        root
        / "deliverables/final-semantic-editorial-qa-v6-4.json"
    )
    ready = (
        root
        / "orchestration/ready-for-final-human-review-v6-4.json"
    )
    publish_dir = root / "publishing/publish-package-v1"
    metadata = publish_dir / "youtube-metadata-v1.json"

    thumbnails = (
        sorted(
            path
            for pattern in (
                "*thumbnail*.png",
                "*thumbnail*.jpg",
                "*thumbnail*.jpeg",
            )
            for path in publish_dir.glob(pattern)
            if path.is_file()
        )
        if publish_dir.is_dir()
        else []
    )

    self._final_video = final if final.is_file() else None
    self._publish_dir = publish_dir if publish_dir.is_dir() else None

    self.labels["episode"].setText(active.episode_id)
    self.labels["video"].setText(
        str(final) if final.is_file() else "غير جاهز بعد"
    )
    self.labels["qa"].setText(
        "PASS" if qa.is_file() else "بانتظار المرحلة النهائية"
    )
    self.labels["review"].setText(
        "READY_FOR_FINAL_HUMAN_REVIEW"
        if ready.is_file()
        else "لم تصل بعد"
    )
    self.labels["metadata"].setText(
        "جاهزة" if metadata.is_file() else "لم تُجهز بعد"
    )
    self.labels["thumbnail"].setText(
        str(thumbnails[0])
        if thumbnails
        else "لم تُجهز بعد"
    )
    self.labels["publish"].setText(
        "HUMAN_ONLY — النشر يدوي"
        if ready.is_file()
        else active.stage_label_ar
    )

    self.open_video_button.setEnabled(
        self._final_video is not None
        and self._final_video.is_file()
    )
    self.open_publish_button.setEnabled(
        self._publish_dir is not None
        and self._publish_dir.is_dir()
    )


def _settings_refresh_v6(self, snapshot) -> None:
    from src.application.siraj_autopilot_v6_6 import (
        inspect_autopilot,
    )

    while self.status_layout.count():
        item = self.status_layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()

    try:
        inspection = inspect_autopilot(snapshot.repo_root)
        status = "ACTIVE"
        stage = V6_STAGE_AR.get(
            inspection.stage,
            inspection.stage,
        )
        action = inspection.action
    except Exception as exc:
        status = "تعذر القراءة: " + str(exc)
        stage = "—"
        action = "—"

    cert = _read_json(
        snapshot.repo_root
        / "projects/_series/"
        "siraj-series-autopilot-backend-certifications-v6.1.json"
    ) or {}
    policy = _read_json(
        snapshot.repo_root
        / "projects/_series/"
        "siraj-cinematic-media-mix-policy-v2.json"
    ) or {}

    values = (
        ("المستودع", str(snapshot.repo_root)),
        ("Autopilot V6", status),
        ("المرحلة الحالية", stage),
        ("الإجراء", action),
        ("Wave 4", str(cert.get("wave4_status") or "ACTIVE")),
        (
            "الفيديو المولد — الحد الأقصى",
            f"{float(policy.get('min_true_video_fraction', 0.50))*100:.2f}%–{float(policy.get('max_true_video_fraction', 0.75))*100:.2f}%",
        ),
        ("إعادة المحاولة المدفوعة", "ممنوعة تلقائيًا"),
        ("الإصلاح المحلي الآمن", "تلقائي"),
        ("الموسيقى", "ممنوعة"),
        ("النشر", "يدوي"),
    )
    for caption, value in values:
        label = QLabel(f"{caption}: {value}")
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.status_layout.addWidget(label)


def install_v6_runtime_bridge() -> None:
    """Install V6 behavior into existing original-dashboard classes."""
    install_v6_stage_label_bridge()

    from . import widgets
    from . import complete_workspace_v1 as workspace

    workflow = widgets.WorkflowStrip
    if not hasattr(
        workflow,
        "_siraj_v6_original_set_episode",
    ):
        workflow._siraj_v6_original_set_episode = workflow.set_episode
        workflow._LABELS = MACRO_LABELS
        workflow.set_episode = _workflow_set_episode

    if not getattr(
        workspace.ApprovalPage.refresh,
        "_siraj_v6_bridge",
        False,
    ):
        _approval_refresh_v6._siraj_v6_bridge = True
        workspace.ApprovalPage.refresh = _approval_refresh_v6

    if not getattr(
        workspace.VideoPublishPage.refresh,
        "_siraj_v6_bridge",
        False,
    ):
        _video_publish_refresh_v6._siraj_v6_bridge = True
        workspace.VideoPublishPage.refresh = _video_publish_refresh_v6

    if not getattr(
        workspace.SettingsPage.refresh,
        "_siraj_v6_bridge",
        False,
    ):
        _settings_refresh_v6._siraj_v6_bridge = True
        workspace.SettingsPage.refresh = _settings_refresh_v6
