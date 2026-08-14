"""User-centred Shorts workflow inside the existing SIRAJ Desktop window.

The surface deliberately exposes five human-sized steps while the existing
workflow service continues to own source admission, hash binding, portfolio
approval, render authorization, automatic QA, human review evidence, and
canonical export.  The UI is presentation/orchestration only; it never adds a
provider, network, paid, upload, retry, or publication capability.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import threading
from typing import Any, Callable, Iterable

from src.application.shorts_derivative_desktop_integration_v1 import ShortsDerivativeDesktopWorkflow
from src.application.shorts_derivative_engine_v1 import HumanReviewSession, ShortsBlockedError
from src.application.shorts_derivative_storage_v1 import ShortsLibraryError
from src.application.shorts_source_discovery_v1 import (
    SourceCandidate,
    SourceDiscoveryResult,
    discover_episode_sources,
)

try:
    from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QProgressBar,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QStackedWidget,
        QTextEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional desktop dependency
    QThread = QDockWidget = QWidget = object  # type: ignore[assignment]
    _QT_AVAILABLE = False

try:  # Multimedia is optional in headless test environments.
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget

    _MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - optional desktop dependency
    QAudioOutput = QMediaPlayer = QVideoWidget = None  # type: ignore[assignment,misc]
    _MULTIMEDIA_AVAILABLE = False


VIDEO_FILE_FILTER = "Video files (*.mp4 *.mov *.mkv *.m4v *.webm *.avi)"
ALL_FILE_FILTER = "All files (*.*)"
SUBTITLE_FILE_FILTER = "Subtitle files (*.srt *.vtt *.json)"
_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}


def desktop_dock_descriptor() -> dict[str, Any]:
    """Expose both the internal contract and the intentionally small UX."""

    return {
        "workflow_id": "SHORTS_DERIVATIVES",
        "label": "Shorts",
        "existing_gui": True,
        "second_gui_created": False,
        "stages": ["SOURCE", "ANALYZE", "CANDIDATES", "PORTFOLIO", "RENDER_PLANS", "LOCAL_RENDERS", "QA_REVIEW", "EXPORT"],
        "visible_stages": ["EPISODE", "SHORTS", "PRODUCE", "REVIEW", "SAVE"],
        "actions": ["Select Episode", "Select Transcript", "Analyze Episode", "View Candidates", "Preview Source Range", "Preview Exact 9:16 Crop", "Keep / Reject", "Reorder Portfolio", "Approve Portfolio", "Generate Local Render Plans", "Approve Local Render", "Local Render", "Cancel Local Render", "Automated QA", "Review Short", "Full Uninterrupted Playback", "Frame Step", "Approve / Reject Short", "Export Approved Short", "Open Shorts Library", "Open Episode Shorts Folder"],
        "hard_boundaries": {
            "provider_calls": False,
            "network_calls": False,
            "paid_calls": False,
            "automatic_publication": False,
            "upload": False,
            "youtube_api": False,
            "public_title_owner": "HUMAN",
            "thumbnail_owner": "HUMAN",
            "real_render": "SIRAJ_DESKTOP_HASH_BOUND_SINGLE_USE",
        },
    }


def configure_episode_file_dialog(dialog: Any) -> None:
    """Apply the critical single-existing-video-file picker contract."""

    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, False)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dialog.setNameFilters([VIDEO_FILE_FILTER, ALL_FILE_FILTER])
    dialog.selectNameFilter(VIDEO_FILE_FILTER)


def configure_transcript_file_dialog(dialog: Any) -> None:
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, False)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dialog.setNameFilters([SUBTITLE_FILE_FILTER, ALL_FILE_FILTER])
    dialog.selectNameFilter(SUBTITLE_FILE_FILTER)


def _friendly_error(raw: str) -> tuple[str, str]:
    code, _, detail = raw.partition(":")
    full = raw.casefold()
    if "BLOCK_AMBIGUOUS_SOURCE" in full or code == "BLOCK_AMBIGUOUS_SOURCE":
        return "وجدنا أكثر من حزمة بيانات محتملة لهذه الحلقة.", code
    if code == "SHORT_TRANSCRIPT_REQUIRED" and "ambiguous" in full:
        return "وجدنا أكثر من مصدر توقيت ولم نختَر بصمت. اختر المصدر الموثوق يدويًا.", code
    messages = {
        "SHORT_SOURCE_MISSING": "تعذر العثور على بيانات الحلقة المطلوبة.",
        "SHORT_SOURCE_HASH_CHANGED": "بيانات الحلقة الموجودة لا تطابق هذا الفيديو. لم يتم اختيارها تلقائيًا.",
        "SHORT_TRANSCRIPT_REQUIRED": "لم يتم العثور على نص زمني لهذه الحلقة.",
        "SHORT_RENDER_PLAN_INVALID": "لا يمكن تجهيز الإنتاج قبل اكتمال اختيار المقاطع.",
        "SHORT_RENDER_AUTHORIZATION_REQUIRED": "لم يبدأ الإنتاج لأن تفويض سطح المكتب غير مكتمل.",
        "SHORT_QA_FAIL": "لم يجتز أحد المقاطع الفحص الآلي.",
        "SHORT_HUMAN_REVIEW_REQUIRED": "تحتاج المقاطع إلى مشاهدة ومراجعة بشرية كاملة.",
        "SHORT_EXPORT_HASH_MISMATCH": "تعذر حفظ الشورت لأن سلامة الملف لم تعد مطابقة.",
        "SHORTS_LIBRARY_UNAVAILABLE": "تعذر الوصول إلى مكتبة Shorts المحلية.",
        "SHORTS_LIBRARY_NOT_FOUND": "لم يتم العثور على مكتبة Shorts المحلية.",
        "SHORTS_EXPORT_CONFLICT": "يوجد ملف محفوظ مسبقًا ولم يتم استبداله.",
        "SHORT_JOB_ALREADY_RUNNING": "هناك عملية جارية بالفعل. انتظر اكتمالها أو أوقفها.",
        "SHORT_RENDER_CANCELLED": "تم إيقاف العملية بأمان ولم يُعتبر الناتج مكتملًا.",
    }
    return messages.get(code, "تعذر إكمال الخطوة الحالية."), code if code else detail


def _format_seconds(value: float | int | None) -> str:
    if value is None:
        return "—"
    total = max(0, int(round(float(value))))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def _display_candidate_type(value: str) -> str:
    return {
        "QUESTION_ANSWER": "سؤال وجواب",
        "CURIOSITY": "فضول واكتشاف",
        "REVELATION": "كشف",
        "STORY_MOMENT": "لحظة قصصية",
        "EMOTIONAL": "لحظة مؤثرة",
        "OTHER_STRONG_STANDALONE": "مقطع مستقل",
    }.get(value, "مقطع قصير")


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
                result = self.function(self.cancel_event)
            except Exception as exc:  # noqa: BLE001 - converted to safe UI error
                self.failed.emit(str(exc))
                return
            self.succeeded.emit(result)

        def cancel(self) -> None:
            self.cancel_event.set()
            self.requestInterruption()


    class _VideoPreview(QFrame):
        position_changed = Signal(int)

        def __init__(self, parent: QWidget | None = None, *, vertical: bool = False) -> None:
            super().__init__(parent)
            self.setObjectName("shortsVideoPreview")
            self.setMinimumHeight(220 if not vertical else 260)
            self.setStyleSheet("QFrame#shortsVideoPreview { background:#050b10; border:1px solid #283746; border-radius:12px; }")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self._player = None
            self._audio = None
            self._video = None
            self._fallback = QLabel("ستظهر المعاينة هنا")
            self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._fallback.setWordWrap(True)
            self._fallback.setStyleSheet("color:#98a8b7; padding:24px;")
            if _MULTIMEDIA_AVAILABLE:
                try:
                    self._player = QMediaPlayer(self)
                    self._audio = QAudioOutput(self)
                    self._video = QVideoWidget(self)
                    self._video.setMinimumHeight(220 if not vertical else 260)
                    self._player.setAudioOutput(self._audio)
                    self._player.setVideoOutput(self._video)
                    self._player.positionChanged.connect(self.position_changed.emit)
                    layout.addWidget(self._video)
                except (AttributeError, RuntimeError):
                    self._player = self._audio = self._video = None
                    layout.addWidget(self._fallback)
            else:
                layout.addWidget(self._fallback)

        @property
        def player_available(self) -> bool:
            return self._player is not None

        def set_source(self, path: Path | str, *, start_seconds: float = 0.0) -> None:
            resolved = Path(path).resolve()
            if self._player is None:
                self._fallback.setText(f"معاينة محلية\n{resolved.name}")
                return
            self._player.setSource(QUrl.fromLocalFile(str(resolved)))
            QTimer.singleShot(80, lambda: self._player and self._player.setPosition(max(0, int(start_seconds * 1000))))

        def play_from_start(self) -> None:
            if self._player is not None:
                self._player.setPosition(0)
                self._player.play()

        def play(self) -> None:
            if self._player is not None:
                self._player.play()

        def pause(self) -> None:
            if self._player is not None:
                self._player.pause()

        def set_position(self, milliseconds: int) -> None:
            if self._player is not None:
                self._player.setPosition(max(0, int(milliseconds)))

        def step(self, milliseconds: int) -> None:
            if self._player is not None:
                self._player.setPosition(max(0, self._player.position() + int(milliseconds)))


    class _CandidateCard(QFrame):
        preview_requested = Signal(object)
        selection_changed = Signal()

        def __init__(self, candidate: Any, number: int, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.candidate = candidate
            self.setObjectName("shortsCandidateCard")
            self.setStyleSheet("QFrame#shortsCandidateCard { background:#0d1721; border:1px solid #283746; border-radius:12px; } QFrame#shortsCandidateCard:hover { border-color:#7b5b21; }")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(7)
            top = QHBoxLayout()
            title = QLabel(f"Short {number:02d}")
            title.setStyleSheet("font-size:15px; font-weight:700; color:#f2f5f7;")
            top.addWidget(title)
            top.addStretch(1)
            self.choose = QCheckBox("اختيار")
            self.choose.toggled.connect(lambda _checked: self.selection_changed.emit())
            top.addWidget(self.choose)
            layout.addLayout(top)
            text = QLabel(str(candidate.text or "—"))
            text.setWordWrap(True)
            text.setStyleSheet("color:#d9e0e5;")
            layout.addWidget(text)
            meta = QLabel(f"{_format_seconds(candidate.end_time - candidate.start_time)}  ·  {_format_seconds(candidate.start_time)} — {_format_seconds(candidate.end_time)}  ·  {_display_candidate_type(candidate.candidate_type)}")
            meta.setStyleSheet("color:#98a8b7; font-size:11px;")
            layout.addWidget(meta)
            score_keys = ("HOOK_STRENGTH", "RETENTION_POTENTIAL", "STANDALONE_CLARITY", "VISUAL_STRENGTH")
            score_names = ("قوة البداية", "الاحتفاظ", "الوضوح", "الجذب")
            score_text: list[str] = []
            for key, name in zip(score_keys, score_names, strict=True):
                dimension = candidate.score_breakdown.get(key)
                if dimension is not None:
                    value = dimension.value if hasattr(dimension, "value") else float(dimension.get("value", 0))
                    score_text.append(f"{name} {round(value * 100)}%")
            scores = QLabel("  ·  ".join(score_text[:4]) or f"التقييم العام {round(candidate.total_score * 100)}%")
            scores.setStyleSheet("color:#e8ad35; font-size:11px;")
            scores.setWordWrap(True)
            layout.addWidget(scores)
            actions = QHBoxLayout()
            self.preview_button = QPushButton("معاينة")
            self.preview_button.clicked.connect(lambda: self.preview_requested.emit(self.candidate))
            actions.addWidget(self.preview_button)
            actions.addStretch(1)
            layout.addLayout(actions)


    class _SourceCandidateDialog(QDialog):
        def __init__(self, candidates: Iterable[SourceCandidate], parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("اختيار حزمة الحلقة")
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.setMinimumSize(680, 430)
            self._candidates = list(candidates)
            self._selected: SourceCandidate | None = None
            layout = QVBoxLayout(self)
            heading = QLabel("وجد SIRAJ أكثر من حزمة بيانات مرتبطة بهذا الفيديو. اختر الحزمة الصحيحة.")
            heading.setWordWrap(True)
            layout.addWidget(heading)
            self.list = QListWidget()
            self.list.setObjectName("sourceCandidatesList")
            self.list.currentRowChanged.connect(self._show_details)
            layout.addWidget(self.list, 1)
            self.details = QLabel()
            self.details.setWordWrap(True)
            self.details.setStyleSheet("color:#98a8b7; padding:8px;")
            layout.addWidget(self.details)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            for candidate in self._candidates:
                item = QListWidgetItem(candidate.path.name)
                item.setToolTip(str(candidate.path))
                self.list.addItem(item)
            if self._candidates:
                self.list.setCurrentRow(0)

        def _show_details(self, row: int) -> None:
            if 0 <= row < len(self._candidates):
                candidate = self._candidates[row]
                self.details.setText(
                    f"الملف: {candidate.path.name}\nالمسار: {candidate.path}\nepisode_id: {candidate.episode_id or 'غير متاح'}\nآخر تعديل: {candidate.modified_time}\nمطابقة المصدر/الهاش: {'نعم' if candidate.source_hash_match else 'غير مثبتة'}"
                )

        def selected_candidate(self) -> SourceCandidate | None:
            row = self.list.currentRow()
            return self._candidates[row] if 0 <= row < len(self._candidates) else None

        def accept(self) -> None:  # noqa: N802 - Qt API
            self._selected = self.selected_candidate()
            if self._selected is None:
                return
            super().accept()


    class ShortsDerivativeDock(QDockWidget):
        """Five-step presentation over the existing hash-bound workflow."""

        _STEP_FOR_STATE = {
            "landing": 0,
            "source": 0,
            "analysis": 0,
            "candidates": 1,
            "portfolio": 1,
            "production": 2,
            "review": 3,
            "save": 4,
            "error": 0,
        }

        def __init__(self, repo_root: Path, parent: QWidget | None = None) -> None:
            super().__init__("Shorts", parent)
            self.repo_root = Path(repo_root).resolve()
            self.workflow = ShortsDerivativeDesktopWorkflow(self.repo_root)
            self._selected_video: Path | None = None
            self._selected_episode_directory: Path | None = None
            self._selected_transcript: Path | None = None
            self._last_discovery: SourceDiscoveryResult | None = None
            self._active_short_id: str | None = None
            self._job: _ShortsJob | None = None
            self._review_session: HumanReviewSession | None = None
            self._candidate_cards: dict[str, _CandidateCard] = {}
            self._review_queue: list[str] = []
            self._review_index = 0
            self._approved_ids: list[str] = []
            self._production_started = False
            self._last_raw_error = ""
            self._state = "landing"
            self.setObjectName("shortsDerivativeDockV1")
            self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self._build_ui()

        def _card(self, object_name: str = "panel") -> QFrame:
            card = QFrame()
            card.setObjectName(object_name)
            card.setStyleSheet(f"QFrame#{object_name} {{ background:#0d1721; border:1px solid #283746; border-radius:12px; }}")
            return card

        def _button(self, text: str, *, primary: bool = False) -> QPushButton:
            button = QPushButton(text)
            if primary:
                button.setObjectName("primaryButton")
            return button

        def _build_ui(self) -> None:
            panel = QWidget(self)
            panel.setMinimumSize(560, 620)
            panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            root = QVBoxLayout(panel)
            root.setContentsMargins(14, 14, 14, 14)
            root.setSpacing(10)

            header = QHBoxLayout()
            title_box = QVBoxLayout()
            title = QLabel("Shorts")
            title.setObjectName("pageTitle")
            title_box.addWidget(title)
            subtitle = QLabel("حوّل حلقاتك إلى مقاطع قصيرة واضحة وجاهزة للمراجعة.")
            subtitle.setWordWrap(True)
            subtitle.setStyleSheet("color:#98a8b7;")
            title_box.addWidget(subtitle)
            header.addLayout(title_box, 1)
            self.details_toggle = QToolButton()
            self.details_toggle.setText("التفاصيل التقنية")
            self.details_toggle.setCheckable(True)
            self.details_toggle.toggled.connect(self._toggle_details)
            header.addWidget(self.details_toggle, 0, Qt.AlignmentFlag.AlignTop)
            root.addLayout(header)

            self.step_labels: list[QLabel] = []
            steps = ("الحلقة", "المقاطع", "الإنتاج", "المراجعة", "الحفظ")
            steps_row = QHBoxLayout()
            steps_row.setSpacing(5)
            for index, label_text in enumerate(steps):
                label = QLabel(label_text)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setMinimumHeight(34)
                label.setProperty("stepIndex", index)
                self.step_labels.append(label)
                steps_row.addWidget(label, 1)
                if index < len(steps) - 1:
                    arrow = QLabel("←")
                    arrow.setStyleSheet("color:#526474;")
                    steps_row.addWidget(arrow, 0)
            root.addLayout(steps_row)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setObjectName("shortsContentScroll")
            content = QWidget()
            self.stack = QStackedWidget(content)
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.addWidget(self.stack)
            scroll.setWidget(content)
            root.addWidget(scroll, 1)

            self._pages: dict[str, QWidget] = {}
            for state, builder in (
                ("landing", self._build_landing_page),
                ("source", self._build_source_page),
                ("analysis", self._build_analysis_page),
                ("candidates", self._build_candidates_page),
                ("portfolio", self._build_portfolio_page),
                ("production", self._build_production_page),
                ("review", self._build_review_page),
                ("save", self._build_save_page),
            ):
                page = builder()
                self._pages[state] = page
                self.stack.addWidget(page)

            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            self.progress.setTextVisible(False)
            self.progress.setFixedHeight(7)
            self.progress.hide()
            root.addWidget(self.progress)
            footer = QHBoxLayout()
            self.status_label = QLabel()
            self.status_label.setWordWrap(True)
            self.status_label.setObjectName("shortsStatus")
            self.status_label.hide()
            footer.addWidget(self.status_label, 1)
            self.cancel_button = self._button("إيقاف بأمان")
            self.cancel_button.clicked.connect(self._cancel_job)
            self.cancel_button.hide()
            footer.addWidget(self.cancel_button)
            root.addLayout(footer)

            self.details = QTextEdit()
            self.details.setReadOnly(True)
            self.details.setMinimumHeight(105)
            self.details.setMaximumHeight(180)
            self.details.hide()
            root.addWidget(self.details)
            self.setWidget(panel)
            self._set_state("landing")

        def _page_layout(self, page: QWidget) -> QVBoxLayout:
            layout = QVBoxLayout(page)
            layout.setContentsMargins(4, 6, 4, 10)
            layout.setSpacing(10)
            return layout

        def _heading(self, layout: QVBoxLayout, title: str, subtitle: str) -> None:
            heading = QLabel(title)
            heading.setObjectName("sectionTitle")
            heading.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            layout.addWidget(heading)
            note = QLabel(subtitle)
            note.setWordWrap(True)
            note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            note.setStyleSheet("color:#98a8b7;")
            layout.addWidget(note)

        def _build_landing_page(self) -> QWidget:
            page = QWidget()
            layout = self._page_layout(page)
            hero = self._card("shortsHeroCard")
            hero_layout = QVBoxLayout(hero)
            hero_layout.setContentsMargins(22, 22, 22, 22)
            mark = QLabel("S")
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            mark.setStyleSheet("color:#e8ad35; font-size:34px; font-weight:800;")
            hero_layout.addWidget(mark)
            welcome = QLabel("حوّل حلقاتك إلى أفضل مقاطع Shorts جاهزة للنشر.")
            welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
            welcome.setWordWrap(True)
            welcome.setStyleSheet("font-size:18px; font-weight:700;")
            hero_layout.addWidget(welcome)
            local = QLabel("يعمل محليًا على جهازك، وتبقى العناوين والصورة المصغرة والنشر بقرار بشري.")
            local.setAlignment(Qt.AlignmentFlag.AlignCenter)
            local.setWordWrap(True)
            local.setStyleSheet("color:#98a8b7;")
            hero_layout.addWidget(local)
            layout.addWidget(hero)
            self.select_button = self._button("اختيار الحلقة", primary=True)
            self.select_button.clicked.connect(self._select_episode)
            layout.addWidget(self.select_button)
            self.open_library_button = self._button("فتح مكتبة الشورتس")
            self.open_library_button.clicked.connect(self._open_library)
            layout.addWidget(self.open_library_button)
            self.advanced_toggle = QToolButton()
            self.advanced_toggle.setText("خيارات متقدمة")
            self.advanced_toggle.setCheckable(True)
            self.advanced_toggle.toggled.connect(self._toggle_advanced_source)
            layout.addWidget(self.advanced_toggle, 0, Qt.AlignmentFlag.AlignRight)
            self.advanced_source_panel = self._card("shortsAdvancedSource")
            advanced_layout = QVBoxLayout(self.advanced_source_panel)
            advanced_layout.addWidget(QLabel("استخدم هذا الخيار فقط عند العمل داخل حزمة SIRAJ معروفة."))
            self.native_select_button = self._button("اختيار مجلد مشروع SIRAJ")
            self.native_select_button.clicked.connect(self._select_native_project)
            advanced_layout.addWidget(self.native_select_button)
            self.advanced_source_panel.hide()
            layout.addWidget(self.advanced_source_panel)
            layout.addStretch(1)
            return page

        def _build_source_page(self) -> QWidget:
            page = QWidget()
            layout = self._page_layout(page)
            self._heading(layout, "الحلقة المختارة", "راجع ملخص المصدر ثم ابدأ التحليل. سيحاول SIRAJ اكتشاف البيانات والنص تلقائيًا.")
            card = self._card("shortsSourceCard")
            grid = QGridLayout(card)
            grid.setContentsMargins(16, 16, 16, 16)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(8)
            self.source_name_label = QLabel("—")
            self.source_name_label.setStyleSheet("font-size:17px; font-weight:700;")
            self.source_id_label = QLabel("—")
            self.source_duration_label = QLabel("—")
            self.source_resolution_label = QLabel("—")
            self.source_audio_label = QLabel("—")
            self.source_transcript_label = QLabel("—")
            self.source_data_label = QLabel("—")
            grid.addWidget(self.source_name_label, 0, 0, 1, 2)
            grid.addWidget(QLabel("المعرّف"), 1, 0)
            grid.addWidget(self.source_id_label, 1, 1)
            grid.addWidget(QLabel("المدة"), 2, 0)
            grid.addWidget(self.source_duration_label, 2, 1)
            grid.addWidget(QLabel("الدقة"), 3, 0)
            grid.addWidget(self.source_resolution_label, 3, 1)
            grid.addWidget(QLabel("الصوت"), 4, 0)
            grid.addWidget(self.source_audio_label, 4, 1)
            grid.addWidget(QLabel("النص"), 5, 0)
            grid.addWidget(self.source_transcript_label, 5, 1)
            grid.addWidget(QLabel("البيانات"), 6, 0)
            grid.addWidget(self.source_data_label, 6, 1)
            layout.addWidget(card)
            self.source_warning = QLabel()
            self.source_warning.setWordWrap(True)
            self.source_warning.setStyleSheet("color:#ef8b36;")
            self.source_warning.hide()
            layout.addWidget(self.source_warning)
            self.history_card = self._card("shortsHistoryCard")
            history_layout = QVBoxLayout(self.history_card)
            history_layout.addWidget(QLabel("Shorts محفوظة لهذه الحلقة"))
            self.history_list = QListWidget()
            self.history_list.setMaximumHeight(115)
            history_layout.addWidget(self.history_list)
            self.history_card.hide()
            layout.addWidget(self.history_card)
            self.analyze_button = self._button("تحليل الحلقة", primary=True)
            self.analyze_button.clicked.connect(self._analyze_episode)
            self.analyze_button.setEnabled(False)
            layout.addWidget(self.analyze_button)
            actions = QHBoxLayout()
            self.transcript_button = self._button("اختيار ملف النص")
            self.transcript_button.clicked.connect(self._select_transcript)
            self.transcript_button.hide()
            actions.addWidget(self.transcript_button)
            self.replace_source_button = self._button("تغيير الحلقة")
            self.replace_source_button.clicked.connect(self._select_episode)
            actions.addWidget(self.replace_source_button)
            actions.addStretch(1)
            layout.addLayout(actions)
            layout.addStretch(1)
            return page

        def _build_analysis_page(self) -> QWidget:
            page = QWidget()
            layout = self._page_layout(page)
            self._heading(layout, "تحليل الحلقة", "يفهم SIRAJ المصدر ويبحث عن المقاطع المناسبة تلقائيًا. يمكنك متابعة العمل بينما تبقى الواجهة مستجيبة.")
            card = self._card("shortsAnalysisCard")
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel("جارٍ قراءة الحلقة…"))
            self.analysis_stage_label = QLabel("جارٍ إعداد الاقتراحات…")
            self.analysis_stage_label.setStyleSheet("color:#e8ad35; font-size:14px;")
            self.analysis_stage_label.setWordWrap(True)
            card_layout.addWidget(self.analysis_stage_label)
            layout.addWidget(card)
            layout.addStretch(1)
            return page

        def _build_candidates_page(self) -> QWidget:
            page = QWidget()
            layout = self._page_layout(page)
            self._heading(layout, "أفضل المقاطع المقترحة", "اختر ما تريد إنتاجه. التفاصيل الفنية متاحة عند الطلب فقط.")
            self.candidate_preview = _VideoPreview()
            self.candidate_preview.setMinimumHeight(190)
            layout.addWidget(self.candidate_preview)
            self.candidates = QListWidget()
            self.candidates.setObjectName("shortsDerivativeCandidatesList")
            self.candidates.setSpacing(8)
            self.candidates.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.candidates.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            layout.addWidget(self.candidates, 1)
            self.zero_candidates_card = self._card("shortsZeroCandidatesCard")
            self.zero_candidates_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            zero_layout = QVBoxLayout(self.zero_candidates_card)
            zero_message = QLabel("لم يجد SIRAJ مقاطع تستحق النشر من هذه الحلقة وفق معايير الجودة الحالية.")
            zero_message.setWordWrap(True)
            zero_message.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            zero_layout.addWidget(zero_message)
            self.show_excluded_button = self._button("عرض المقاطع المستبعدة")
            self.show_excluded_button.clicked.connect(self._show_excluded_candidates)
            zero_layout.addWidget(self.show_excluded_button)
            self.zero_candidates_card.hide()
            layout.addWidget(self.zero_candidates_card)
            self.continue_button = self._button("متابعة للإنتاج", primary=True)
            self.continue_button.clicked.connect(self._continue_to_portfolio)
            self.continue_button.setEnabled(False)
            layout.addWidget(self.continue_button)
            return page

        def _build_portfolio_page(self) -> QWidget:
            page = QWidget()
            layout = self._page_layout(page)
            self._heading(layout, "المقاطع المختارة", "يمكنك إعادة ترتيبها بالسحب، ثم متابعة تجهيز الإنتاج.")
            self.portfolio_list = QListWidget()
            self.portfolio_list.setObjectName("shortsPortfolioList")
            self.portfolio_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            self.portfolio_list.setDefaultDropAction(Qt.DropAction.MoveAction)
            self.portfolio_list.setMinimumHeight(180)
            layout.addWidget(self.portfolio_list)
            self.schedule_toggle = QToolButton()
            self.schedule_toggle.setText("إضافة يوم النشر المقترح (اختياري)")
            self.schedule_toggle.setCheckable(True)
            self.schedule_toggle.toggled.connect(self._toggle_schedule)
            layout.addWidget(self.schedule_toggle, 0, Qt.AlignmentFlag.AlignRight)
            self.schedule_combo = QComboBox()
            self.schedule_combo.addItems(["من دون تحديد", "السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة"])
            self.schedule_combo.hide()
            layout.addWidget(self.schedule_combo)
            self.portfolio_button = self._button("متابعة", primary=True)
            self.portfolio_button.clicked.connect(self._continue_from_portfolio)
            layout.addWidget(self.portfolio_button)
            return page

        def _build_production_page(self) -> QWidget:
            page = QWidget()
            layout = self._page_layout(page)
            self._heading(layout, "جاهز للإنتاج", "أُعدت المقاطع داخليًا مع ربط المصدر والهاش. لا يبدأ الإنتاج إلا بالنقرة التالية.")
            self.production_summary = QLabel()
            self.production_summary.setWordWrap(True)
            self.production_summary.setStyleSheet("font-size:15px; font-weight:700;")
            layout.addWidget(self.production_summary)
            self.production_list = QListWidget()
            self.production_list.setObjectName("shortsProductionList")
            self.production_list.setMinimumHeight(150)
            layout.addWidget(self.production_list)
            self.crop_preview = _VideoPreview(vertical=True)
            self.crop_preview.setMinimumHeight(240)
            self.crop_preview.hide()
            layout.addWidget(self.crop_preview)
            actions = QHBoxLayout()
            self.crop_button = self._button("معاينة القص 9:16")
            self.crop_button.clicked.connect(self._toggle_crop_preview)
            actions.addWidget(self.crop_button)
            actions.addStretch(1)
            layout.addLayout(actions)
            self.produce_button = self._button("إنتاج الشورتس", primary=True)
            self.produce_button.clicked.connect(self._start_production)
            layout.addWidget(self.produce_button)
            self.production_note = QLabel("بعد الإنتاج يبدأ الفحص الآلي تلقائيًا، ثم تُطلب المراجعة البشرية.")
            self.production_note.setWordWrap(True)
            self.production_note.setStyleSheet("color:#98a8b7;")
            layout.addWidget(self.production_note)
            return page

        def _build_review_page(self) -> QWidget:
            page = QWidget()
            layout = self._page_layout(page)
            self._heading(layout, "المراجعة", "شاهد كل شورت كاملًا من البداية إلى النهاية، ثم افحص التفاصيل قبل الاعتماد.")
            self.review_preview = _VideoPreview()
            self.review_preview.position_changed.connect(self._on_review_position)
            layout.addWidget(self.review_preview)
            review_meta = QHBoxLayout()
            self.review_counter_label = QLabel("Short — من —")
            self.review_counter_label.setStyleSheet("font-size:14px; font-weight:700;")
            review_meta.addWidget(self.review_counter_label)
            review_meta.addStretch(1)
            self.review_duration_label = QLabel("—")
            review_meta.addWidget(self.review_duration_label)
            layout.addLayout(review_meta)
            self.review_progress = QProgressBar()
            self.review_progress.setRange(0, 100)
            self.review_progress.setValue(0)
            self.review_progress.setTextVisible(False)
            self.review_progress.setFixedHeight(8)
            layout.addWidget(self.review_progress)
            self.review_progress_label = QLabel("المراجعة البشرية مطلوبة")
            self.review_progress_label.setStyleSheet("color:#e8ad35;")
            layout.addWidget(self.review_progress_label)
            self.start_full_button = self._button("بدء المشاهدة الكاملة", primary=True)
            self.start_full_button.clicked.connect(self._start_full_playback)
            layout.addWidget(self.start_full_button)
            self.detail_button = self._button("الفحص التفصيلي")
            self.detail_button.clicked.connect(self._show_detail_review)
            self.detail_button.setEnabled(False)
            layout.addWidget(self.detail_button)
            self.detail_toolbar = self._card("shortsDetailToolbar")
            detail_layout = QVBoxLayout(self.detail_toolbar)
            self.review_slider = QSlider(Qt.Orientation.Horizontal)
            self.review_slider.setRange(0, 1000)
            self.review_slider.sliderMoved.connect(self._review_seek)
            detail_layout.addWidget(self.review_slider)
            controls = QHBoxLayout()
            self.pause_button = self._button("إيقاف/تشغيل")
            self.pause_button.clicked.connect(self._toggle_review_playback)
            controls.addWidget(self.pause_button)
            self.frame_back_button = self._button("إطار سابق")
            self.frame_back_button.clicked.connect(lambda: self._detail_step(-1))
            controls.addWidget(self.frame_back_button)
            self.frame_forward_button = self._button("إطار لاحق")
            self.frame_forward_button.clicked.connect(lambda: self._detail_step(1))
            controls.addWidget(self.frame_forward_button)
            detail_layout.addLayout(controls)
            self.detail_toolbar.hide()
            layout.addWidget(self.detail_toolbar)
            self.review_checklist: list[QCheckBox] = []
            checklist_card = self._card("shortsReviewChecklist")
            checklist_layout = QVBoxLayout(checklist_card)
            checklist_layout.addWidget(QLabel("قائمة المراجعة البشرية"))
            for text in ("لا توجد وجوه بشرية ظاهرة", "الستر صحيح", "المشاهد مرتبطة بالكلام", "القص العمودي مناسب", "الصوت سليم", "لا توجد أخطاء أو قطع غير طبيعي", "الإيقاع مناسب", "المقطع يبدو احترافيًا"):
                check = QCheckBox(text)
                self.review_checklist.append(check)
                checklist_layout.addWidget(check)
            layout.addWidget(checklist_card)
            actions = QHBoxLayout()
            self.approve_review_button = self._button("اعتماد الشورت", primary=True)
            self.approve_review_button.clicked.connect(self._approve_review)
            actions.addWidget(self.approve_review_button)
            self.reject_review_button = self._button("رفض الشورت")
            self.reject_review_button.clicked.connect(self._reject_review)
            actions.addWidget(self.reject_review_button)
            layout.addLayout(actions)
            return page

        def _build_save_page(self) -> QWidget:
            page = QWidget()
            layout = self._page_layout(page)
            self._heading(layout, "الحفظ", "أصبح الشورت معتمدًا بشريًا. احفظه في مكتبة Shorts المحلية عندما تكون مستعدًا.")
            card = self._card("shortsSaveCard")
            card_layout = QVBoxLayout(card)
            self.save_message = QLabel()
            self.save_message.setWordWrap(True)
            self.save_message.setStyleSheet("font-size:16px; font-weight:700; color:#72e3a5;")
            card_layout.addWidget(self.save_message)
            self.save_location_label = QLabel()
            self.save_location_label.setWordWrap(True)
            self.save_location_label.setStyleSheet("color:#98a8b7;")
            card_layout.addWidget(self.save_location_label)
            self.saved_list = QListWidget()
            self.saved_list.setMaximumHeight(160)
            card_layout.addWidget(self.saved_list)
            layout.addWidget(card)
            self.save_button = self._button("حفظ الشورت", primary=True)
            self.save_button.clicked.connect(self._save_approved)
            layout.addWidget(self.save_button)
            actions = QHBoxLayout()
            self.open_episode_button = self._button("فتح مجلد الحلقة")
            self.open_episode_button.clicked.connect(self._open_episode_folder)
            actions.addWidget(self.open_episode_button)
            self.save_open_library_button = self._button("فتح مكتبة الشورتس")
            self.save_open_library_button.clicked.connect(self._open_library)
            actions.addWidget(self.save_open_library_button)
            layout.addLayout(actions)
            return page

        def _set_state(self, state: str) -> None:
            self._state = state
            page = self._pages.get(state)
            if page is not None:
                self.stack.setCurrentWidget(page)
            active = self._STEP_FOR_STATE.get(state, 0)
            for index, label in enumerate(self.step_labels):
                if index < active:
                    marker, color, background = "✓", "#39c477", "#103325"
                elif index == active:
                    marker, color, background = "●", "#e8ad35", "#332714"
                else:
                    marker, color, background = "○", "#98a8b7", "#111e29"
                label.setText(f"{marker}  {('الحلقة', 'المقاطع', 'الإنتاج', 'المراجعة', 'الحفظ')[index]}")
                label.setStyleSheet(f"color:{color}; background:{background}; border:1px solid {color}; border-radius:8px; padding:6px 3px; font-weight:600;")
            self._refresh_details()

        def _set_message(self, text: str, tone: str = "muted") -> None:
            self.status_label.setText(text)
            self.status_label.show()
            colors = {"ok": "#72e3a5", "warning": "#ef8b36", "error": "#e65f5f", "muted": "#98a8b7"}
            self.status_label.setStyleSheet(f"color:{colors.get(tone, colors['muted'])}; padding:5px 2px;")

        def _toggle_details(self, visible: bool) -> None:
            self.details.setVisible(visible)
            if visible:
                self._refresh_details()

        def _toggle_advanced_source(self, visible: bool) -> None:
            self.advanced_source_panel.setVisible(visible)

        def _toggle_schedule(self, visible: bool) -> None:
            self.schedule_combo.setVisible(visible)

        def _refresh_details(self) -> None:
            if not hasattr(self, "details"):
                return
            status: dict[str, Any] = {}
            try:
                status = asdict(self.workflow.status())
            except Exception:  # pragma: no cover - diagnostics must never break UI
                status = {"state": "UNAVAILABLE"}
            payload = {
                "ui_state": self._state,
                "workflow_status": status,
                "selected_video": None if self._selected_video is None else str(self._selected_video),
                "discovery": None if self._last_discovery is None else self._last_discovery.to_dict(),
                "raw_error": self._last_raw_error,
                "safety_boundaries": {"provider_calls": 0, "network_calls": 0, "paid_calls": 0, "upload": False, "automatic_publication": False},
            }
            self.details.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

        def _begin_job(self, function: Callable[[threading.Event], Any], success: Callable[[Any], None], *, message: str) -> None:
            if self._job is not None and self._job.isRunning():
                self._show_error(ShortsBlockedError("SHORT_JOB_ALREADY_RUNNING", "WAIT_OR_CANCEL_CURRENT_JOB"))
                return
            self._job = _ShortsJob(function, self)
            self._job.progress.connect(lambda value: self._set_message(value))
            self._job.succeeded.connect(success)
            self._job.failed.connect(lambda value: self._show_error(RuntimeError(value)))
            self._job.finished.connect(self._job_finished)
            self.progress.show()
            self.cancel_button.show()
            self._set_message(message)
            self._job.start()

        def _job_finished(self) -> None:
            self.progress.hide()
            self.cancel_button.hide()
            self._job = None
            self._refresh_details()

        def _pick_episode_file(self) -> Path | None:
            dialog = QFileDialog(self, "اختيار فيديو الحلقة")
            dialog.setDirectory(str(self._selected_episode_directory or Path.home()))
            configure_episode_file_dialog(dialog)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            selected = dialog.selectedFiles()
            if len(selected) != 1:
                self._show_error(ShortsBlockedError("SHORT_SOURCE_MISSING", "SINGLE_VIDEO_FILE_REQUIRED"))
                return None
            path = Path(selected[0]).resolve()
            if path.suffix.casefold() not in _VIDEO_SUFFIXES:
                self._show_error(ShortsBlockedError("SHORT_SOURCE_MISSING", "VIDEO_FILE_REQUIRED"))
                return None
            return path

        def _pick_transcript_file(self) -> Path | None:
            dialog = QFileDialog(self, "اختيار ملف النص")
            dialog.setDirectory(str(self._selected_episode_directory or Path.home()))
            configure_transcript_file_dialog(dialog)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            selected = dialog.selectedFiles()
            return Path(selected[0]).resolve() if len(selected) == 1 else None

        def _select_episode(self) -> None:
            path = self._pick_episode_file()
            if path is None:
                return
            self._selected_video = path
            self._selected_episode_directory = path.parent
            self._selected_transcript = None
            self._last_discovery = discover_episode_sources(path, repo_root=self.repo_root)
            discovery = self._last_discovery
            if discovery.status == "STALE_SOURCE":
                self._show_error(ShortsBlockedError("SHORT_SOURCE_HASH_CHANGED", "STALE_METADATA_HASH"))
                return
            if discovery.metadata_ambiguous:
                dialog = _SourceCandidateDialog(discovery.metadata_candidates, self)
                if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_candidate() is None:
                    self._set_message("لم يتم اختيار حزمة البيانات.", "warning")
                    return
                self._ingest_discovered(path, dialog.selected_candidate(), discovery.matched_transcript)
                return
            self._ingest_discovered(path, discovery.matched_metadata, discovery.matched_transcript)

        def _ingest_discovered(self, video: Path, metadata: SourceCandidate | None, transcript: SourceCandidate | None) -> None:
            if metadata is not None and metadata.source_hash_match is False:
                self._show_error(ShortsBlockedError("SHORT_SOURCE_HASH_CHANGED", "STALE_METADATA_HASH"))
                return
            try:
                episode = self.workflow.select_episode(
                    mode="VIDEO_PLUS_TRANSCRIPT",
                    video_path=video,
                    metadata_path=None if metadata is None else metadata.path,
                    transcript_path=None if transcript is None else transcript.path,
                )
            except (ShortsBlockedError, OSError, ValueError, ShortsLibraryError) as error:
                self._show_error(error)
                return
            self._render_admission(episode)

        def _select_transcript(self) -> None:
            if self._selected_video is None:
                self._show_error(ShortsBlockedError("SHORT_SOURCE_MISSING", "SELECT_EPISODE_FIRST"))
                return
            path = self._pick_transcript_file()
            if path is None:
                return
            self._selected_transcript = path
            metadata = self._last_discovery.matched_metadata if self._last_discovery is not None else None
            self._ingest_discovered(self._selected_video, metadata, SourceCandidate(path, None, None, True, "manual-selection", 100, None, "الآن"))

        def _select_native_project(self) -> None:
            directory = QFileDialog.getExistingDirectory(self, "اختيار مجلد مشروع SIRAJ", str(self._selected_episode_directory or Path.home()))
            if not directory:
                return
            self._selected_episode_directory = Path(directory).resolve()
            try:
                episode = self.workflow.select_episode(mode="SIRAJ_NATIVE_EPISODE", episode_directory=self._selected_episode_directory)
            except (ShortsBlockedError, OSError, ValueError, ShortsLibraryError) as error:
                self._show_error(error)
                return
            self._selected_video = Path(episode.source_video_path).resolve()
            self._render_admission(episode)

        def _render_admission(self, episode: Any) -> None:
            admission = episode.source_admission
            self.source_name_label.setText(episode.episode_display_name or episode.episode_id)
            self.source_id_label.setText(episode.episode_id)
            self.source_duration_label.setText(_format_seconds(episode.source_duration_seconds))
            dimensions = episode.metadata.get("dimensions", episode.metadata.get("video_dimensions")) if isinstance(episode.metadata, dict) else None
            self.source_resolution_label.setText(f"{dimensions.get('width')}×{dimensions.get('height')}" if isinstance(dimensions, dict) and dimensions.get("width") and dimensions.get("height") else "متاحة في التفاصيل")
            self.source_audio_label.setText("متاح ✓" if episode.has_audio is True else "غير متاح")
            self.source_transcript_label.setText("مكتمل ✓" if admission.get("transcript_bound") else "مطلوب")
            self.source_data_label.setText("مطابقة ✓" if admission.get("metadata_bound") else "تحتاج اختيارًا")
            self.analyze_button.setEnabled(admission.get("status") == "PASS")
            self.transcript_button.setVisible(not bool(admission.get("transcript_bound")))
            self.source_warning.setVisible(not bool(admission.get("transcript_bound")))
            if not admission.get("transcript_bound"):
                self.source_warning.setText("لم يتم العثور على نص زمني للحلقة. اختر ملف SRT أو VTT أو JSON للمتابعة.")
            else:
                self.source_warning.clear()
            self._populate_history(episode.episode_id, episode.episode_display_name)
            self._set_state("source")
            self._set_message("الحلقة جاهزة للتحليل ✓", "ok" if admission.get("status") == "PASS" else "warning")

        def _populate_history(self, episode_id: str, display_name: str) -> None:
            self.history_list.clear()
            try:
                binding = self.workflow.library.resolve(create=False)
                folder = self.workflow.library.episode_directory(episode_id, display_name, create=False)
                files = sorted((folder / "Shorts").glob("*.mp4")) if (folder / "Shorts").is_dir() else []
            except (ShortsLibraryError, OSError):
                files = []
            for path in files:
                item = QListWidgetItem(path.stem)
                item.setToolTip(str(path))
                self.history_list.addItem(item)
            self.history_card.setVisible(bool(files))

        def _analyze_episode(self) -> None:
            if self.workflow.episode is None:
                self._show_error(ShortsBlockedError("SHORT_SOURCE_MISSING", "SELECT_EPISODE_FIRST"))
                return
            self._set_state("analysis")
            self.analysis_stage_label.setText("جارٍ قراءة الحلقة وفهم محتواها…")
            self._begin_job(lambda _cancel: self.workflow.analyze_episode(), self._analysis_ready, message="جارٍ إعداد أفضل المقاطع…")

        def _analysis_ready(self, analysis: Any) -> None:
            self.candidates.clear()
            self._candidate_cards.clear()
            eligible = [candidate for candidate in analysis.candidates if candidate.status == "PASS"]
            candidate_page = self._pages.get("candidates")
            candidate_page_layout = candidate_page.layout() if candidate_page is not None else None
            candidate_layout_index = candidate_page_layout.indexOf(self.candidates) if candidate_page_layout is not None else -1
            self.zero_candidates_card.setVisible(not bool(eligible))
            self.continue_button.setVisible(bool(eligible))
            self.continue_button.setEnabled(False)
            if not eligible:
                # An empty result is a first-class user outcome.  Hide the
                # video preview and candidate list so the explanation and
                # recovery action remain visible without a giant empty pane.
                self.candidate_preview.hide()
                self.candidates.hide()
                self.candidate_preview.setMinimumHeight(0)
                self.candidate_preview.setMaximumHeight(0)
                self.candidates.setMinimumHeight(0)
                self.candidates.setMaximumHeight(0)
                if candidate_page_layout is not None and candidate_layout_index >= 0:
                    candidate_page_layout.setStretch(candidate_layout_index, 0)
                self.candidate_preview.updateGeometry()
                self.candidates.updateGeometry()
                self._set_state("candidates")
                if candidate_page_layout is not None:
                    candidate_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                    for heading_index in (0, 1):
                        heading_item = candidate_page_layout.itemAt(heading_index)
                        heading_widget = heading_item.widget() if heading_item is not None else None
                        if heading_widget is not None:
                            heading_widget.setMaximumHeight(
                                max(heading_widget.sizeHint().height(), heading_widget.minimumSizeHint().height())
                            )
                self.zero_candidates_card.setMaximumHeight(
                    max(self.zero_candidates_card.sizeHint().height(), self.zero_candidates_card.minimumSizeHint().height())
                )
                self._refresh_candidate_layout()
                self._set_message("لم يجد SIRAJ مقاطع تستحق النشر وفق معايير الجودة الحالية.", "warning")
                self._refresh_details()
                return
            if candidate_page_layout is not None:
                candidate_page_layout.setAlignment(Qt.AlignmentFlag(0))
                for heading_index in (0, 1):
                    heading_item = candidate_page_layout.itemAt(heading_index)
                    heading_widget = heading_item.widget() if heading_item is not None else None
                    if heading_widget is not None:
                        heading_widget.setMaximumHeight(16777215)
            self.zero_candidates_card.setMaximumHeight(16777215)
            self.candidate_preview.setMinimumHeight(190)
            self.candidate_preview.setMaximumHeight(16777215)
            self.candidates.setMinimumHeight(0)
            self.candidates.setMaximumHeight(16777215)
            if candidate_page_layout is not None and candidate_layout_index >= 0:
                candidate_page_layout.setStretch(candidate_layout_index, 1)
            self.candidate_preview.show()
            self.candidates.show()
            self._refresh_candidate_layout()
            for number, candidate in enumerate(eligible, start=1):
                item = QListWidgetItem()
                card = _CandidateCard(candidate, number)
                card.preview_requested.connect(self._preview_candidate)
                card.selection_changed.connect(self._refresh_candidate_action)
                item.setSizeHint(card.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, candidate.candidate_id)
                self.candidates.addItem(item)
                self.candidates.setItemWidget(item, card)
                self._candidate_cards[candidate.candidate_id] = card
            self._set_state("candidates")
            self._set_message("تم إعداد المقاطع المقترحة. اختر ما تريد.", "ok")

        def _refresh_candidate_layout(self) -> None:
            page = self._pages.get("candidates")
            if page is not None and page.layout() is not None:
                page.layout().invalidate()
                page.updateGeometry()
            content = self.stack.parentWidget()
            if content is not None and content.layout() is not None:
                content.layout().invalidate()
                content.adjustSize()
                content.updateGeometry()
            self.stack.updateGeometry()

        def _refresh_candidate_action(self) -> None:
            self.continue_button.setEnabled(bool(self._checked_candidate_ids()))
            self._refresh_details()

        def _checked_candidate_ids(self) -> list[str]:
            return [candidate_id for candidate_id, card in self._candidate_cards.items() if card.choose.isChecked()]

        def _preview_candidate(self, candidate: Any) -> None:
            if self._selected_video is None:
                return
            self._active_short_id = None
            self.candidate_preview.set_source(self._selected_video, start_seconds=float(candidate.start_time))
            QTimer.singleShot(140, self.candidate_preview.play)
            self._set_message("المعاينة داخل SIRAJ جاهزة.", "ok")
            self.details.setPlainText(json.dumps({"candidate_id": candidate.candidate_id, "source_range": [candidate.start_time, candidate.end_time], "score_evidence": {key: (value.to_dict() if hasattr(value, "to_dict") else value) for key, value in candidate.score_breakdown.items()}, "constitution": dict(candidate.policy_result)}, ensure_ascii=False, indent=2, default=str))

        def _show_excluded_candidates(self) -> None:
            if self.workflow.analysis is None:
                return
            excluded = [candidate for candidate in self.workflow.analysis.candidates if candidate.status != "PASS"]
            self.details.setPlainText("\n".join(f"{candidate.candidate_id}: {', '.join(candidate.rejection_reasons) or candidate.status}" for candidate in excluded) or "لا توجد مقاطع مستبعدة.")
            self.details_toggle.setChecked(True)

        def _continue_to_portfolio(self) -> None:
            selected = self._checked_candidate_ids()
            if not selected:
                self._set_message("اختر مقطعًا واحدًا على الأقل للمتابعة.", "warning")
                return
            try:
                portfolio = self.workflow.select_candidates(selected, reviewed=True)
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)
                return
            self.portfolio_list.clear()
            ordered = list(portfolio.recommended_order or portfolio.selected_candidate_ids)
            by_id = {candidate.candidate_id: candidate for candidate in self.workflow.analysis.candidates} if self.workflow.analysis else {}
            for index, candidate_id in enumerate(ordered, start=1):
                candidate = by_id.get(candidate_id)
                label = f"Short {index:02d}  ·  {_format_seconds((candidate.end_time - candidate.start_time) if candidate else None)}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, candidate_id)
                self.portfolio_list.addItem(item)
            self._set_state("portfolio")
            self._set_message("راجع ترتيب المقاطع ثم تابع.", "ok")

        def _continue_from_portfolio(self) -> None:
            ordered = [self.portfolio_list.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.portfolio_list.count())]
            ordered = [value for value in ordered if isinstance(value, str)]
            if not ordered:
                self._show_error(ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PORTFOLIO_REQUIRED"))
                return
            day = self.schedule_combo.currentText() if self.schedule_toggle.isChecked() and self.schedule_combo.currentIndex() else None
            self.workflow.set_longform_publish_day(day)
            try:
                self.workflow.select_candidates(ordered, reviewed=True)
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)
                return
            self._set_state("production")
            self.produce_button.setEnabled(False)
            self._begin_job(lambda _cancel: self.workflow.generate_render_plans(), self._plans_ready, message="جارٍ تجهيز المقاطع للإنتاج…")

        def _plans_ready(self, plans: Any) -> None:
            plans = tuple(plans)
            self.production_list.clear()
            self.production_summary.setText(f"{len(plans)} Shorts جاهزة للإنتاج")
            for index, plan in enumerate(plans, start=1):
                item = QListWidgetItem(f"Short {index:02d}  ·  {_format_seconds(plan.expected_duration)}  ·  جاهز للإنتاج")
                item.setData(Qt.ItemDataRole.UserRole, plan.short_id)
                self.production_list.addItem(item)
            self.produce_button.setEnabled(bool(plans))
            self._set_message("تم تجهيز الإنتاج. انقر عند استعدادك.", "ok")
            self._refresh_details()

        def _toggle_crop_preview(self) -> None:
            visible = not self.crop_preview.isVisible()
            self.crop_preview.setVisible(visible)
            if visible and self._selected_video is not None:
                self.crop_preview.set_source(self._selected_video)
                self._set_message("هذه معاينة داخلية للقص العمودي؛ الإحداثيات التقنية مخفية.", "muted")

        def _start_production(self) -> None:
            if self._production_started:
                self._set_message("بدأت هذه العملية بالفعل ولا توجد إعادة إرسال تلقائية.", "warning")
                return
            if not self.workflow.render_plans:
                self._show_error(ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PLAN_NOT_FOUND"))
                return
            self._production_started = True
            self.produce_button.setEnabled(False)
            short_ids = list(self.workflow.render_plans)
            self._set_message("جارٍ إنتاج الشورتس ثم فحصها تلقائيًا…")
            self._begin_job(lambda cancel: self._render_all_and_qa(short_ids, cancel), self._production_finished, message="جارٍ إنتاج الشورتس…")

        def _render_all_and_qa(self, short_ids: list[str], cancel: threading.Event) -> list[tuple[str, Any, Any]]:
            results: list[tuple[str, Any, Any]] = []
            for short_id in short_ids:
                if cancel.is_set():
                    raise ShortsBlockedError("SHORT_RENDER_CANCELLED", "USER_CANCELLED")
                # The Produce button is the explicit Desktop human click.  The
                # envelope is issued immediately before each render so a
                # cancellation cannot leave a queue of unused authorizations.
                self.workflow.approve_local_render(short_id)
                render = self.workflow.render_local(short_id, cancel_event=cancel)
                qa = self.workflow.inspect_qa(short_id)
                results.append((short_id, render, qa))
            return results

        def _production_finished(self, results: list[tuple[str, Any, Any]]) -> None:
            failed = [short_id for short_id, _render, qa in results if qa.status != "SHORT_QA_PASS" or not qa.technical_qa_pass]
            if failed:
                self._set_message("لم يجتز أحد المقاطع الفحص الآلي. لم تتم المتابعة إلى المراجعة.", "error")
                self._show_error(ShortsBlockedError("SHORT_QA_FAIL", "AUTOMATED_CHECK_FAILED"))
                return
            self._review_queue = [short_id for short_id, _render, _qa in results]
            self._review_index = 0
            self._approved_ids = []
            self._load_review_short()

        def _load_review_short(self) -> None:
            if not self._review_queue:
                self._set_state("save")
                return
            self._active_short_id = self._review_queue[self._review_index]
            try:
                self._review_session = self.workflow.begin_human_review(self._active_short_id)
                render = self.workflow.render_results[self._active_short_id]
                self.review_preview.set_source(Path(render.output_path))
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)
                return
            self.review_counter_label.setText(f"Short {self._review_index + 1} من {len(self._review_queue)}")
            self.review_duration_label.setText(_format_seconds(self._review_session.duration_seconds))
            self.review_progress.setValue(0)
            self.review_progress_label.setText("المراجعة البشرية مطلوبة")
            self.review_slider.setValue(0)
            self.detail_toolbar.hide()
            self.detail_button.setEnabled(False)
            for check in self.review_checklist:
                check.setChecked(False)
            self._set_state("review")
            self._set_message("الفحص الآلي ناجح ✓ — المراجعة البشرية مطلوبة.", "ok")

        def _start_full_playback(self) -> None:
            if self._review_session is None:
                return
            self._review_session.start_playback()
            self.review_preview.play_from_start()
            self.review_progress_label.setText("المشاهدة الكاملة جارية…")
            self._set_message("أكمل المشاهدة من البداية إلى النهاية من دون بحث.")

        def _on_review_position(self, milliseconds: int) -> None:
            if self._review_session is None:
                return
            self._review_session.observe_position(milliseconds / 1000.0)
            duration = max(0.1, self._review_session.duration_seconds)
            percent = min(100, round(self._review_session.playback_coverage_seconds / duration * 100))
            self.review_progress.setValue(percent)
            self.review_slider.blockSignals(True)
            self.review_slider.setValue(min(1000, round(milliseconds / 1000.0 / duration * 1000)))
            self.review_slider.blockSignals(False)
            if self._review_session.valid:
                self.review_progress_label.setText("المشاهدة الكاملة مكتملة ✓")
                self.detail_button.setEnabled(True)

        def _show_detail_review(self) -> None:
            if self._review_session is None or not self._review_session.valid:
                self._set_message("أكمل المشاهدة الكاملة أولًا.", "warning")
                return
            self._review_session.record_detail_inspection()
            self.detail_toolbar.show()
            self._set_message("الفحص التفصيلي متاح الآن.", "ok")

        def _toggle_review_playback(self) -> None:
            if self.review_preview.player_available:
                # The preview intentionally owns playback; the evidence tracker
                # only observes its position and never fabricates completion.
                if self.review_preview._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    self.review_preview.pause()
                else:
                    self.review_preview._player.play()

        def _review_seek(self, value: int) -> None:
            if self._review_session is None:
                return
            position = self._review_session.duration_seconds * value / 1000.0
            self._review_session.record_seek(position)
            self.review_preview.set_position(int(position * 1000))
            self.review_progress.setValue(0)
            self.detail_button.setEnabled(False)
            self._set_message("أعيدت المشاهدة الكاملة إلى البداية بسبب البحث.", "warning")

        def _detail_step(self, direction: int) -> None:
            if self._review_session is None or not self.detail_toolbar.isVisible():
                return
            self._review_session.record_detail_inspection()
            self.review_preview.step(direction * 42)
            self._set_message("تم فحص إطار من المراجعة التفصيلية.", "muted")

        def _all_review_checks_pass(self) -> bool:
            return all(check.isChecked() for check in self.review_checklist)

        def _approve_review(self) -> None:
            if self._active_short_id is None or self._review_session is None or not self._review_session.valid:
                self._show_error(ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "FULL_REVIEW_REQUIRED"))
                return
            if self._review_session.detailed_inspection_count <= 0:
                self._set_message("افتح الفحص التفصيلي قبل اعتماد الشورت.", "warning")
                return
            if not self._all_review_checks_pass():
                self._set_message("أكمل قائمة المراجعة البشرية قبل الاعتماد.", "warning")
                return
            try:
                self.workflow.complete_human_review(self._active_short_id, reviewer="SIRAJ Desktop Human", decision="APPROVE", constitutional_review=True, quality_review=True)
            except (ShortsBlockedError, OSError, ValueError) as error:
                self._show_error(error)
                return
            self._approved_ids.append(self._active_short_id)
            self._review_index += 1
            if self._review_index < len(self._review_queue):
                self._load_review_short()
            else:
                self.save_message.setText("اكتملت المراجعة البشرية لكل الشورتس.")
                self.save_location_label.setText("سيُحفظ في: سطح المكتب > SIRAJ Shorts > مجلد الحلقة")
                self.save_button.setEnabled(True)
                self._set_state("save")
                self._set_message("تم اعتماد الشورتس. الخطوة التالية هي الحفظ.", "ok")

        def _reject_review(self) -> None:
            self._set_message("تم رفض الشورت ولم يُحفظ. لا توجد إعادة إنتاج تلقائية.", "warning")
            self.save_button.setEnabled(False)
            self._set_state("save")
            self.save_message.setText("لم يتم اعتماد هذا الشورت.")
            self.save_location_label.setText("يمكنك الاحتفاظ بالتفاصيل للمراجعة اللاحقة.")

        def _save_approved(self) -> None:
            if not self._approved_ids:
                self._set_message("لا يوجد شورت معتمد للحفظ.", "warning")
                return
            manifests: list[dict[str, Any]] = []
            try:
                for short_id in self._approved_ids:
                    manifests.append(self.workflow.export_short(short_id))
            except (ShortsBlockedError, OSError, ValueError, ShortsLibraryError) as error:
                self._show_error(error)
                return
            self.saved_list.clear()
            for manifest in manifests:
                self.saved_list.addItem(Path(str(manifest.get("render", {}).get("path", "Short"))).stem)
            episode_dir = manifests[0].get("episode_directory") if manifests else None
            if episode_dir:
                folder = Path(str(episode_dir))
                self.save_location_label.setText(f"تم الحفظ في: سطح المكتب > SIRAJ Shorts > {folder.name}")
            self.save_message.setText("تم حفظ الشورت بنجاح ✓")
            self.save_button.setEnabled(False)
            self._set_message("تم الحفظ في مكتبة Shorts المحلية.", "ok")
            self._refresh_details()

        def _cancel_job(self) -> None:
            if self._job is not None and self._job.isRunning():
                self._job.cancel()
                self._set_message("جارٍ إيقاف العملية بأمان…", "warning")

        def _show_error(self, error: Exception) -> None:
            raw = str(error)
            self._last_raw_error = raw
            friendly, code = _friendly_error(raw)
            self._set_message(friendly, "error")
            self._refresh_details()
            if code in {"SHORT_TRANSCRIPT_REQUIRED", "SHORT_SOURCE_MISSING", "SHORT_SOURCE_HASH_CHANGED"} and self._selected_video is not None:
                self._set_state("source")
                self.transcript_button.show()
                self.source_warning.setText(friendly)
                self.source_warning.show()
            elif "BLOCK_AMBIGUOUS_SOURCE" in raw:
                self._set_state("source")
            else:
                self._set_state(self._state if self._state != "landing" else "error")

        def _open_library(self) -> None:
            try:
                self._open_local_path(self.workflow.open_library())
            except (ShortsBlockedError, ShortsLibraryError, OSError) as error:
                self._show_error(error)

        def _open_episode_folder(self) -> None:
            try:
                self._open_local_path(self.workflow.open_episode_folder())
            except (ShortsBlockedError, ShortsLibraryError, OSError) as error:
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


__all__ = [
    "ALL_FILE_FILTER",
    "ShortsDerivativeDock",
    "SUBTITLE_FILE_FILTER",
    "VIDEO_FILE_FILTER",
    "configure_episode_file_dialog",
    "configure_transcript_file_dialog",
    "desktop_dock_descriptor",
    "install_shorts_derivative_dock",
]
