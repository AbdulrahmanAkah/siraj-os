from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.application.autonomous_episode_orchestrator_v1 import (
    load_orchestrator_state,
)
from src.application.production_resume_router_v1 import (
    resolve_resume_directive,
)

from .models import DashboardSnapshot, EpisodeRecord
from .widgets import MetricCard, Panel, StatusPill

RELEASE = "SIRAJ_DESKTOP_COMPLETE_WORKSPACE_AND_RESUME_V1"

OpenProduction = Callable[[], None]
OpenPath = Callable[[Path], None]


def _json_status(path: Path) -> str:
    if not path.is_file():
        return "غير موجود"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "ملف غير صالح"
    if not isinstance(payload, dict):
        return "بيانات غير صالحة"
    for key in (
        "status",
        "decision",
        "human_approval",
        "publish_ready",
        "final_video_approval",
    ):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return "متاح"


def _human_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def _episode_root(snapshot: DashboardSnapshot) -> Path | None:
    active = snapshot.active_episode
    return active.project_path if active is not None else None


def _safe_read_preview(path: Path, maximum_chars: int = 35_000) -> str:
    if not path.is_file():
        return "الملف غير موجود."
    if path.suffix.lower() not in {
        ".json",
        ".txt",
        ".md",
        ".yaml",
        ".yml",
        ".csv",
        ".srt",
    }:
        return (
            f"الملف: {path.name}\n"
            f"الحجم: {_human_size(path.stat().st_size)}\n"
            "استخدم زر فتح الملف لعرضه في البرنامج الافتراضي."
        )
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return "تعذر قراءة الملف: " + str(exc)
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
            text = json.dumps(payload, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    if len(text) > maximum_chars:
        text = text[:maximum_chars] + "\n… [تم اختصار المعاينة]"
    return text


class _PageBase(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("completeWorkspaceSectionScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        shell.addWidget(scroll)

        self.content = QWidget()
        self.content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(18, 16, 18, 20)
        self.body.setSpacing(12)
        scroll.setWidget(self.content)

        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        heading.setWordWrap(True)
        self.body.addWidget(heading)
        intro = QLabel(subtitle)
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        self.body.addWidget(intro)

    def refresh(self, snapshot: DashboardSnapshot) -> None:
        del snapshot


class EpisodeCataloguePage(_PageBase):
    def __init__(
        self,
        title: str,
        subtitle: str,
        open_production: OpenProduction,
        open_path: OpenPath,
    ) -> None:
        super().__init__(title, subtitle)
        self._open_production = open_production
        self._open_path = open_path
        self._episodes: tuple[EpisodeRecord, ...] = ()

        cards = QWidget()
        self.cards_layout = QGridLayout(cards)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.body.addWidget(cards)

        self.table = QTableWidget(0, 8)
        self.table.setObjectName("completeWorkspaceEpisodeTable")
        self.table.setHorizontalHeaderLabels(
            (
                "الحلقة",
                "المرحلة",
                "المدة",
                "اللقطات",
                "المعتمدة",
                "المنتجة",
                "الجاهزية",
                "الإجراء التالي",
            )
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 8):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self.table.setMinimumHeight(300)
        self.body.addWidget(self.table)

        actions = QHBoxLayout()
        self.continue_button = QPushButton("استكمال إنتاج الحلقة")
        self.continue_button.setObjectName("workspaceContinueEpisodeButton")
        self.continue_button.setMinimumHeight(44)
        self.continue_button.clicked.connect(self._open_production)
        actions.addWidget(self.continue_button)
        self.open_folder_button = QPushButton("فتح مجلد الحلقة")
        self.open_folder_button.setObjectName("workspaceOpenEpisodeFolderButton")
        self.open_folder_button.clicked.connect(self._open_selected_folder)
        actions.addWidget(self.open_folder_button)
        actions.addStretch(1)
        self.body.addLayout(actions)
        self.body.addStretch(1)

    def _selected_episode(self) -> EpisodeRecord | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._episodes):
            return self._episodes[0] if self._episodes else None
        item = self.table.item(row, 0)
        episode_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        for episode in self._episodes:
            if episode.episode_id == episode_id:
                return episode
        return None

    def _open_selected_folder(self) -> None:
        episode = self._selected_episode()
        if episode is not None:
            self._open_path(episode.project_path)

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def refresh(self, snapshot: DashboardSnapshot) -> None:
        self._episodes = snapshot.episodes
        self._clear_cards()
        metrics = (
            MetricCard("المشاريع", str(len(snapshot.episodes)), "المجلدات المكتشفة"),
            MetricCard("قيد العمل", str(len(snapshot.work_queue)), "تحتاج متابعة"),
            MetricCard("جاهزة للتحويل", str(len(snapshot.ready_for_conversion)), "طابور الفيديو"),
            MetricCard("جاهزة للنشر", str(len(snapshot.publish_ready)), "اجتازت المراجعات"),
        )
        for index, card in enumerate(metrics):
            self.cards_layout.addWidget(card, index // 2, index % 2)
            self.cards_layout.setColumnStretch(index % 2, 1)

        self.table.setRowCount(len(snapshot.episodes))
        for row, episode in enumerate(snapshot.episodes):
            readiness = (
                "جاهزة للنشر"
                if episode.publish_ready
                else "جاهزة للتحويل"
                if episode.conversion_ready
                else "قيد العمل"
            )
            values = (
                f"{episode.title_ar} — {episode.episode_id}",
                episode.stage_label_ar,
                episode.duration_label,
                str(episode.shot_count),
                str(episode.approved_shot_count),
                str(episode.generated_shot_count),
                readiness,
                episode.next_action_ar,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, episode.episode_id)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        if snapshot.episodes:
            self.table.selectRow(0)
        self.continue_button.setEnabled(bool(snapshot.episodes))
        self.open_folder_button.setEnabled(bool(snapshot.episodes))


class ArtifactBrowserPage(_PageBase):
    def __init__(
        self,
        title: str,
        subtitle: str,
        patterns: Sequence[str],
        open_path: OpenPath,
        *,
        include_external_reports: bool = False,
    ) -> None:
        super().__init__(title, subtitle)
        self._patterns = tuple(patterns)
        self._open_path = open_path
        self._include_external_reports = include_external_reports
        self._paths: list[Path] = []

        self.summary = QLabel("")
        self.summary.setObjectName("sectionTitle")
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("completeWorkspaceArtifactTable")
        self.table.setHorizontalHeaderLabels(
            ("الملف", "النوع", "الحجم", "المسار")
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(260)
        self.table.itemSelectionChanged.connect(self._preview_selected)
        self.body.addWidget(self.table)

        self.preview = QPlainTextEdit()
        self.preview.setObjectName("completeWorkspaceArtifactPreview")
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(220)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.body.addWidget(self.preview)

        actions = QHBoxLayout()
        self.open_file_button = QPushButton("فتح الملف المحدد")
        self.open_file_button.clicked.connect(self._open_selected)
        actions.addWidget(self.open_file_button)
        self.open_folder_button = QPushButton("فتح مجلد الملف")
        self.open_folder_button.clicked.connect(self._open_selected_folder)
        actions.addWidget(self.open_folder_button)
        actions.addStretch(1)
        self.body.addLayout(actions)
        self.body.addStretch(1)

    def _selected_path(self) -> Path | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._paths):
            return self._paths[row]
        return self._paths[0] if self._paths else None

    def _preview_selected(self) -> None:
        path = self._selected_path()
        self.preview.setPlainText(
            _safe_read_preview(path) if path is not None else "لا توجد ملفات."
        )

    def _open_selected(self) -> None:
        path = self._selected_path()
        if path is not None:
            self._open_path(path)

    def _open_selected_folder(self) -> None:
        path = self._selected_path()
        if path is not None:
            self._open_path(path.parent)

    def _collect(self, snapshot: DashboardSnapshot) -> list[Path]:
        root = _episode_root(snapshot)
        found: set[Path] = set()
        if root is not None:
            for pattern in self._patterns:
                found.update(path for path in root.glob(pattern) if path.is_file())
        if self._include_external_reports:
            siraj_root = snapshot.repo_root.parent.parent
            reports = siraj_root / "Reports"
            if reports.is_dir():
                found.update(path for path in reports.rglob("*") if path.is_file())
        return sorted(
            found,
            key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
            reverse=True,
        )[:250]

    def refresh(self, snapshot: DashboardSnapshot) -> None:
        self._paths = self._collect(snapshot)
        active = snapshot.active_episode
        episode_label = active.episode_id if active is not None else "لا توجد حلقة"
        self.summary.setText(
            f"الحلقة النشطة: {episode_label} — الملفات المعروضة: {len(self._paths)}"
        )
        self.table.setRowCount(len(self._paths))
        for row, path in enumerate(self._paths):
            try:
                relative = str(path.relative_to(snapshot.repo_root))
            except ValueError:
                relative = str(path)
            values = (
                path.name,
                path.suffix.lower().lstrip(".") or "ملف",
                _human_size(path.stat().st_size),
                relative,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {1, 2}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        enabled = bool(self._paths)
        self.open_file_button.setEnabled(enabled)
        self.open_folder_button.setEnabled(enabled)
        if enabled:
            self.table.selectRow(0)
        else:
            self.preview.setPlainText("لا توجد ملفات مطابقة في الحلقة النشطة.")


class ApprovalPage(_PageBase):
    def __init__(self, open_production: OpenProduction, open_path: OpenPath) -> None:
        super().__init__(
            "الاعتمادات والبوابات البشرية",
            "تعرض هذه الصفحة اعتماد نطاق الحلقة، ونتيجة QA، وقرار المراجعة النهائية، وحالة حزمة النشر.",
        )
        self._open_production = open_production
        self._open_path = open_path
        self._paths: list[Path | None] = []

        self.current_directive = QLabel("")
        self.current_directive.setObjectName("sectionTitle")
        self.current_directive.setWordWrap(True)
        self.body.addWidget(self.current_directive)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(("البوابة", "الحالة", "الدليل"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(260)
        self.body.addWidget(self.table)

        actions = QHBoxLayout()
        continue_button = QPushButton("فتح المرحلة المطلوبة")
        continue_button.setMinimumHeight(44)
        continue_button.clicked.connect(self._open_production)
        actions.addWidget(continue_button)
        self.open_evidence_button = QPushButton("فتح دليل الاعتماد")
        self.open_evidence_button.clicked.connect(self._open_evidence)
        actions.addWidget(self.open_evidence_button)
        actions.addStretch(1)
        self.body.addLayout(actions)
        self.body.addStretch(1)

    def _open_evidence(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._paths):
            path = self._paths[row]
            if path is not None and path.is_file():
                self._open_path(path)

    def refresh(self, snapshot: DashboardSnapshot) -> None:
        active = snapshot.active_episode
        if active is None:
            rows: list[tuple[str, str, Path | None]] = []
            self.current_directive.setText("لا توجد حلقة نشطة.")
        else:
            root = active.project_path
            rows = [
                (
                    "اعتماد الموضوع والأحداث",
                    _json_status(root / "contracts/approved-scope-v1.json"),
                    root / "contracts/approved-scope-v1.json",
                ),
                (
                    "الفحص الآلي QA",
                    _json_status(root / "qa/automatic-qa-report-v1.json"),
                    root / "qa/automatic-qa-report-v1.json",
                ),
                (
                    "المراجعة البشرية النهائية",
                    _json_status(root / "publishing/human-final-review-v1.json"),
                    root / "publishing/human-final-review-v1.json",
                ),
                (
                    "حزمة النشر",
                    _json_status(
                        root
                        / "publishing/publish-package-v1/publish-manifest-v1.json"
                    ),
                    root
                    / "publishing/publish-package-v1/publish-manifest-v1.json",
                ),
            ]
            directive = resolve_resume_directive(snapshot.repo_root)
            self.current_directive.setText(
                "المرحلة المطلوبة الآن: "
                + directive.label_ar
                + " — "
                + directive.detail_ar
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
        self.open_evidence_button.setEnabled(bool(rows))


class VideoPublishPage(_PageBase):
    def __init__(self, open_production: OpenProduction, open_path: OpenPath) -> None:
        super().__init__(
            "الفيديو وحزمة النشر",
            "مركز الوصول إلى الحلقة النهائية وQA وبيانات YouTube وحزمة الرفع اليدوي.",
        )
        self._open_production = open_production
        self._open_path = open_path
        self._final_video: Path | None = None
        self._publish_dir: Path | None = None

        panel = Panel()
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setSpacing(10)
        fields = (
            ("episode", "الحلقة"),
            ("video", "الفيديو النهائي"),
            ("qa", "الفحص الآلي"),
            ("review", "المراجعة النهائية"),
            ("metadata", "بيانات YouTube"),
            ("thumbnail", "الصورة المصغرة"),
            ("publish", "حالة النشر"),
        )
        self.labels: dict[str, QLabel] = {}
        for row, (key, caption) in enumerate(fields):
            caption_label = QLabel(caption + ":")
            value = QLabel("—")
            value.setObjectName("muted")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(caption_label, row, 1)
            grid.addWidget(value, row, 0)
            self.labels[key] = value
        grid.setColumnStretch(0, 1)
        self.body.addWidget(panel)

        note = QLabel(
            "سراج يجهز الفيديو وQA والعنوان والوصف والوسوم وقائمة الرفع. "
            "رفع YouTube والنقر على نشر يبقيان يدويين. إذا لم توجد صورة مصغرة "
            "فستظهر كعنصر ناقص بوضوح بدل الادعاء بأن الحزمة مكتملة."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        self.body.addWidget(note)

        actions = QHBoxLayout()
        continue_button = QPushButton("استكمال الحلقة حتى حزمة النشر")
        continue_button.setObjectName("workspaceFinishToPublishButton")
        continue_button.setMinimumHeight(46)
        continue_button.clicked.connect(self._open_production)
        actions.addWidget(continue_button)
        self.open_video_button = QPushButton("عرض الحلقة النهائية")
        self.open_video_button.clicked.connect(self._open_video)
        actions.addWidget(self.open_video_button)
        self.open_publish_button = QPushButton("فتح حزمة النشر")
        self.open_publish_button.clicked.connect(self._open_publish)
        actions.addWidget(self.open_publish_button)
        actions.addStretch(1)
        self.body.addLayout(actions)
        self.body.addStretch(1)

    def _open_video(self) -> None:
        if self._final_video is not None and self._final_video.is_file():
            self._open_path(self._final_video)

    def _open_publish(self) -> None:
        if self._publish_dir is not None and self._publish_dir.is_dir():
            self._open_path(self._publish_dir)

    def refresh(self, snapshot: DashboardSnapshot) -> None:
        active = snapshot.active_episode
        if active is None:
            for label in self.labels.values():
                label.setText("لا توجد حلقة نشطة")
            self._final_video = None
            self._publish_dir = None
        else:
            root = active.project_path
            final = root / "deliverables/episode-master-v1.mp4"
            if not final.is_file() and active.final_video_path is not None:
                final = active.final_video_path
            qa = root / "qa/automatic-qa-report-v1.json"
            review = root / "publishing/human-final-review-v1.json"
            publish_dir = root / "publishing/publish-package-v1"
            metadata = publish_dir / "youtube-metadata-v1.json"
            thumbnail_candidates = sorted(
                path
                for pattern in (
                    "*thumbnail*.png",
                    "*thumbnail*.jpg",
                    "*thumbnail*.jpeg",
                )
                for path in publish_dir.glob(pattern)
                if path.is_file()
            ) if publish_dir.is_dir() else []
            self._final_video = final if final.is_file() else None
            self._publish_dir = publish_dir if publish_dir.is_dir() else None
            self.labels["episode"].setText(active.episode_id)
            self.labels["video"].setText(
                str(final) if final.is_file() else "غير جاهز"
            )
            self.labels["qa"].setText(_json_status(qa))
            self.labels["review"].setText(_json_status(review))
            self.labels["metadata"].setText(
                "جاهزة" if metadata.is_file() else "غير جاهزة"
            )
            self.labels["thumbnail"].setText(
                str(thumbnail_candidates[0])
                if thumbnail_candidates
                else "غير موجودة — تحتاج إعدادًا قبل الرفع"
            )
            self.labels["publish"].setText(
                "READY_TO_PUBLISH"
                if (publish_dir / "publish-manifest-v1.json").is_file()
                else active.stage_label_ar
            )
        self.open_video_button.setEnabled(
            self._final_video is not None and self._final_video.is_file()
        )
        self.open_publish_button.setEnabled(
            self._publish_dir is not None and self._publish_dir.is_dir()
        )


class SettingsPage(_PageBase):
    def __init__(self, repo_root: Path, open_production: OpenProduction, open_path: OpenPath) -> None:
        super().__init__(
            "الإعدادات وحالة النظام",
            "إعدادات التشغيل، حدود الأتمتة، مسارات المشروع، وحالة مفاتيح المزودين.",
        )
        self.repo_root = repo_root
        self._open_production = open_production
        self._open_path = open_path

        self.status_box = QGroupBox("حالة البيئة")
        self.status_layout = QVBoxLayout(self.status_box)
        self.body.addWidget(self.status_box)

        policy = QLabel(
            "السياسات الملزمة: حد الحلقة 40$، لا إنفاق مدفوع دون تأكيد، "
            "لا موسيقى، إصلاح جزئي فقط، بوابتان بشريتان، ورفع YouTube يدوي."
        )
        policy.setWordWrap(True)
        policy.setObjectName("muted")
        self.body.addWidget(policy)

        actions = QHBoxLayout()
        production = QPushButton("فتح إعدادات الإنتاج والمفاتيح")
        production.clicked.connect(self._open_production)
        actions.addWidget(production)
        repo = QPushButton("فتح المستودع")
        repo.clicked.connect(lambda: self._open_path(self.repo_root))
        actions.addWidget(repo)
        reports = QPushButton("فتح تقارير سراج")
        reports.clicked.connect(
            lambda: self._open_path(self.repo_root.parent.parent / "Reports")
        )
        actions.addWidget(reports)
        actions.addStretch(1)
        self.body.addLayout(actions)
        self.body.addStretch(1)

    def refresh(self, snapshot: DashboardSnapshot) -> None:
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        try:
            state = load_orchestrator_state(snapshot.repo_root)
            status = str(state.get("status", "UNKNOWN"))
            stage = str(state.get("stage", "UNKNOWN"))
        except Exception as exc:
            status = "تعذر القراءة: " + str(exc)
            stage = "—"
        report_root = snapshot.repo_root.parent.parent / "Reports"
        values = (
            ("المستودع", str(snapshot.repo_root)),
            ("تقارير سراج", str(report_root)),
            ("حالة المنسق", status),
            ("المرحلة الحالية", stage),
            ("الإصدار", RELEASE),
        )
        for caption, value in values:
            label = QLabel(f"{caption}: {value}")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.status_layout.addWidget(label)


class CompleteWorkspace(QStackedWidget):
    SECTION_ORDER = (
        "dashboard",
        "projects",
        "episodes",
        "storyboard",
        "visual",
        "video",
        "approvals",
        "reports",
        "settings",
    )

    def __init__(
        self,
        repo_root: Path,
        open_production: OpenProduction,
        open_path: OpenPath,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root.resolve()
        self._pages: dict[str, QWidget] = {}
        self._refreshable: list[_PageBase] = []
        self._open_production = open_production
        self._open_path = open_path
        self.setObjectName("completeWorkspaceStack")

        self._add(
            "projects",
            EpisodeCataloguePage(
                "المشاريع",
                "إدارة جميع مشاريع الحلقات ومراحلها وملفاتها من مكان واحد.",
                open_production,
                open_path,
            ),
        )
        self._add(
            "episodes",
            EpisodeCataloguePage(
                "الحلقات",
                "متابعة كل حلقة من المسودة إلى READY_TO_PUBLISH مع الإجراء التالي الحقيقي.",
                open_production,
                open_path,
            ),
        )
        self._add(
            "storyboard",
            ArtifactBrowserPage(
                "الستوريبورد والخطة التحريرية",
                "استعراض النص والبحث والستوريبورد وخطط اللقطات الخاصة بالحلقة النشطة.",
                (
                    "**/*storyboard*.json",
                    "**/*script*.json",
                    "**/*research*.json",
                    "**/*shot-plan*.json",
                    "contracts/approved-scope-v1.json",
                ),
                open_path,
            ),
        )
        self._add(
            "visual",
            ArtifactBrowserPage(
                "الحزم البصرية",
                "استعراض حزم اللقطات والصور والفيديوهات والجرافيك والإيصالات المرئية.",
                (
                    "cinematic/shot-packages/**/*",
                    "generated/**/*",
                    "graphics/**/*",
                    "outputs/**/*",
                    "video/**/*",
                ),
                open_path,
            ),
        )
        self._add(
            "video",
            VideoPublishPage(open_production, open_path),
        )
        self._add(
            "approvals",
            ApprovalPage(open_production, open_path),
        )
        self._add(
            "reports",
            ArtifactBrowserPage(
                "التقارير وسجلات التدقيق",
                "تقارير QA والمراجعة والنشر وسجلات التشغيل المحلية الخاصة بسراج.",
                (
                    "qa/**/*",
                    "orchestration/**/*report*.json",
                    "publishing/**/*",
                    "evidence/**/*",
                ),
                open_path,
                include_external_reports=True,
            ),
        )
        self._add(
            "settings",
            SettingsPage(self.repo_root, open_production, open_path),
        )

    def _add(self, key: str, page: _PageBase) -> None:
        self._pages[key] = page
        self._refreshable.append(page)
        self.addWidget(page)

    def set_dashboard(self, widget: QWidget) -> None:
        if "dashboard" in self._pages:
            old = self._pages["dashboard"]
            self.removeWidget(old)
        self._pages["dashboard"] = widget
        self.insertWidget(0, widget)
        self.setCurrentWidget(widget)

    def show_section(self, key: str) -> bool:
        page = self._pages.get(key)
        if page is None:
            return False
        self.setCurrentWidget(page)
        return True

    def refresh(self, snapshot: DashboardSnapshot) -> None:
        for page in self._refreshable:
            page.refresh(snapshot)
