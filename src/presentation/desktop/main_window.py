from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import DashboardSnapshot, EpisodeRecord, EpisodeStage
from .repository import build_dashboard_snapshot
from .theme import APP_STYLESHEET, COLORS
from .widgets import MetricCard, Panel, PreviewCanvas, StatusPill, WorkflowStrip


class SirajDesktopWindow(QMainWindow):
    def __init__(self, repo_root: Path) -> None:
        super().__init__()
        self.repo_root = repo_root
        self.snapshot = build_dashboard_snapshot(repo_root)
        self.setWindowTitle("سراج — إدارة إنتاج الحلقات")
        self.resize(1540, 930)
        self.setMinimumSize(1180, 720)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_ui()
        self._populate(self.snapshot)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setDirection(QBoxLayout.Direction.LeftToRight)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)
        outer.addWidget(self._build_sidebar())
        outer.addWidget(self._build_workspace(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(5)

        brand = QLabel("SIRAJ")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        subtitle = QLabel("نظام الإنتاج التاريخي")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        navigation = (
            ("▦  لوحة التحكم", True),
            ("▤  المشاريع", False),
            ("▶  الحلقات", False),
            ("▥  الستوريبورد", False),
            ("◇  الحزم البصرية", False),
            ("🎬  الفيديو", False),
            ("✓  الاعتمادات", False),
            ("▥  التقارير", False),
            ("⚙  الإعدادات", False),
        )
        for text, active in navigation:
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setProperty("active", active)
            button.clicked.connect(
                lambda checked=False, label=text: self._show_placeholder(label)
            )
            layout.addWidget(button)

        layout.addStretch(1)
        status_panel = Panel()
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(10, 10, 10, 10)
        status_layout.addWidget(QLabel("النظام"))
        health = QLabel("● جميع الأنظمة تعمل بكفاءة")
        health.setStyleSheet(f"color: {COLORS['green']};")
        health.setWordWrap(True)
        status_layout.addWidget(health)
        path_label = QLabel(str(self.repo_root))
        path_label.setObjectName("muted")
        path_label.setWordWrap(True)
        status_layout.addWidget(path_label)
        layout.addWidget(status_panel)
        return sidebar

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        workspace.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setDirection(QBoxLayout.Direction.LeftToRight)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_layout.addWidget(self._build_hero())
        left_layout.addWidget(self._build_episode_queue())
        left_layout.addWidget(WorkflowStrip())
        left_layout.addWidget(self._build_lower_dashboard())
        left_layout.addStretch(1)

        right_column = QWidget()
        right_column.setMaximumWidth(420)
        right_column.setMinimumWidth(330)
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        right_layout.addWidget(self._build_preview(), 2)
        right_layout.addWidget(self._build_episode_details())
        right_layout.addWidget(self._build_activities(), 1)

        body_layout.addWidget(left_column, 3)
        body_layout.addWidget(right_column, 2)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        return workspace

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("headerPanel")
        layout = QHBoxLayout(header)
        layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ابحث في المشاريع، الحلقات، اللقطات…")
        self.search_input.textChanged.connect(self._filter_episode_rows)
        layout.addWidget(self.search_input, 1)

        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(210)
        self.project_combo.currentIndexChanged.connect(self._select_episode)
        layout.addWidget(self.project_combo)

        environment = StatusPill("● Production", "green")
        layout.addWidget(environment)

        refresh = QPushButton("↻ تحديث")
        refresh.clicked.connect(self._refresh)
        layout.addWidget(refresh)
        return header

    def _build_hero(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("heroPanel")
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(8)

        title = QLabel("مشروع سراج — إدارة إنتاج الحلقات")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("من النص والستوريبورد حتى الفيديو الجاهز للنشر")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        badges = QHBoxLayout()
        badges.setDirection(QBoxLayout.Direction.RightToLeft)
        self.active_episode_badge = StatusPill("الحلقة النشطة: —", "muted")
        self.shot_count_badge = StatusPill("0 لقطة", "blue")
        self.model_badge = StatusPill("النموذج: —", "muted")
        self.hero_status_badge = StatusPill("الحالة: —", "gold")
        badges.addWidget(self.active_episode_badge)
        badges.addWidget(self.shot_count_badge)
        badges.addWidget(self.model_badge)
        badges.addWidget(self.hero_status_badge)
        badges.addStretch(1)
        layout.addLayout(badges)
        return hero

    def _build_episode_queue(self) -> QWidget:
        queue = QFrame()
        queue.setObjectName("queuePanel")
        layout = QVBoxLayout(queue)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        heading = QLabel("الحلقات الجاهزة للتحويل إلى فيديو جاهز للنشر على يوتيوب")
        heading.setObjectName("sectionTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"color: {COLORS['gold']}; padding: 13px;")
        layout.addWidget(heading)

        self.episode_table = QTableWidget(0, 6)
        self.episode_table.setHorizontalHeaderLabels(
            ("الحلقة", "الحالة", "المدة", "عدد اللقطات", "جاهزية التحويل", "إجراء")
        )
        self.episode_table.setAlternatingRowColors(True)
        self.episode_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.episode_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.episode_table.verticalHeader().setVisible(False)
        header = self.episode_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in range(1, 6):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        self.episode_table.itemSelectionChanged.connect(self._episode_selection_changed)
        layout.addWidget(self.episode_table)
        return queue

    def _build_preview(self) -> QWidget:
        panel = Panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        title_row = QHBoxLayout()
        title = QLabel("معاينة")
        title.setObjectName("sectionTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(StatusPill("16:9", "muted"))
        layout.addLayout(title_row)

        self.preview = PreviewCanvas()
        layout.addWidget(self.preview, 1)

        controls = QHBoxLayout()
        for label in ("|◀", "◀", "▶", "▶|", "⛶"):
            button = QPushButton(label)
            button.setEnabled(label == "⛶")
            controls.addWidget(button)
        layout.addLayout(controls)
        return panel

    def _build_episode_details(self) -> QWidget:
        panel = Panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        title = QLabel("تفاصيل الحلقة النشطة")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.detail_labels: dict[str, QLabel] = {}
        fields = (
            ("episode", "معرّف الحلقة"),
            ("shot", "المشهد الحالي"),
            ("model", "النموذج الأساسي"),
            ("provider", "المزوّد"),
            ("shots", "اللقطات المعتمدة"),
            ("safety", "السلامة البصرية"),
        )
        for key, caption in fields:
            row = QHBoxLayout()
            row.addWidget(QLabel(caption + ":"))
            value = QLabel("—")
            value.setObjectName("muted")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(value, 1)
            layout.addLayout(row)
            self.detail_labels[key] = value
        return panel

    def _build_activities(self) -> QWidget:
        panel = Panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        title = QLabel("النشاطات الأخيرة")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.activities_list = QListWidget()
        layout.addWidget(self.activities_list)
        return panel

    def _build_lower_dashboard(self) -> QWidget:
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        outputs_panel = Panel()
        outputs_layout = QVBoxLayout(outputs_panel)
        outputs_layout.setContentsMargins(12, 10, 12, 12)
        outputs_layout.addWidget(QLabel("المخرجات والملفات"))
        self.outputs_list = QListWidget()
        outputs_layout.addWidget(self.outputs_list, 1)
        open_outputs = QPushButton("فتح مجلد المشروع")
        open_outputs.clicked.connect(self._open_repo_root)
        outputs_layout.addWidget(open_outputs)

        log_panel = Panel()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(12, 10, 12, 12)
        log_layout.addWidget(QLabel("سجل التنفيذ"))
        self.execution_log = QPlainTextEdit()
        self.execution_log.setReadOnly(True)
        self.execution_log.setMaximumBlockCount(200)
        log_layout.addWidget(self.execution_log, 1)

        metrics = QWidget()
        metrics_layout = QGridLayout(metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(10)
        self.metric_host = metrics_layout

        grid.addWidget(outputs_panel, 0, 0, 2, 1)
        grid.addWidget(log_panel, 0, 1, 2, 1)
        grid.addWidget(metrics, 0, 2, 2, 1)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)
        return container

    def _populate(self, snapshot: DashboardSnapshot) -> None:
        self.snapshot = snapshot
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for episode in snapshot.episodes:
            self.project_combo.addItem(
                f"{episode.title_ar} — {episode.episode_id}",
                episode.episode_id,
            )
        self.project_combo.blockSignals(False)
        self._populate_episode_table(snapshot.episodes)
        self._populate_outputs(snapshot)
        self._populate_activities(snapshot)
        self._populate_metrics(snapshot)
        active = snapshot.active_episode
        if active is not None:
            self._display_episode(active)
        else:
            self.preview.set_context("لا توجد حلقات مكتشفة", "—")
        self._log("PASS_DESKTOP_DATA_REFRESH")
        for warning in snapshot.warnings:
            self._log("WARNING " + warning)

    def _populate_episode_table(self, episodes: tuple[EpisodeRecord, ...]) -> None:
        self.episode_table.setRowCount(0)
        for episode in episodes:
            row = self.episode_table.rowCount()
            self.episode_table.insertRow(row)
            title = QTableWidgetItem(f"{episode.title_ar} — {episode.episode_id}")
            title.setData(Qt.ItemDataRole.UserRole, episode.episode_id)
            self.episode_table.setItem(row, 0, title)
            self.episode_table.setItem(row, 1, QTableWidgetItem(episode.stage_label_ar))
            self.episode_table.setItem(row, 2, QTableWidgetItem(episode.duration_label))
            self.episode_table.setItem(row, 3, QTableWidgetItem(str(episode.shot_count)))
            readiness_text = "جاهز" if episode.conversion_ready else "غير مكتمل"
            if episode.publish_ready:
                readiness_text = "جاهز للنشر"
            self.episode_table.setItem(row, 4, QTableWidgetItem(readiness_text))

            action = QPushButton(episode.next_action_ar)
            action.setObjectName("primaryButton" if episode.conversion_ready else "")
            action.clicked.connect(
                lambda checked=False, item=episode: self._episode_action(item)
            )
            self.episode_table.setCellWidget(row, 5, action)
        if episodes:
            self.episode_table.selectRow(0)

    def _populate_outputs(self, snapshot: DashboardSnapshot) -> None:
        self.outputs_list.clear()
        for path in snapshot.output_files:
            item = str(path.relative_to(snapshot.repo_root))
            self.outputs_list.addItem("▧  " + item)
        if not snapshot.output_files:
            self.outputs_list.addItem("لا توجد مخرجات قابلة للعرض بعد")

    def _populate_activities(self, snapshot: DashboardSnapshot) -> None:
        self.activities_list.clear()
        for activity in snapshot.activities:
            self.activities_list.addItem(
                f"{activity.time_label}  •  {activity.message_ar}"
            )
        if not snapshot.activities:
            self.activities_list.addItem("لا توجد نشاطات حديثة")

    def _populate_metrics(self, snapshot: DashboardSnapshot) -> None:
        while self.metric_host.count():
            item = self.metric_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        metrics = (
            MetricCard(
                "المقاطع المنتجة",
                str(snapshot.generated_clip_count),
                "من ملفات الحلقات الحالية",
            ),
            MetricCard(
                "اللقطات المعتمدة",
                str(snapshot.approved_shot_count),
                f"من {snapshot.total_shot_count}",
            ),
            MetricCard(
                "التكلفة المسجلة",
                f"${snapshot.estimated_cost_usd:,.2f}",
                "تُحدّث من إيصالات المزوّد",
            ),
            MetricCard(
                "جاهزية النشر",
                f"{snapshot.readiness_percent}%",
                "الحلقات ذات الفيديو النهائي المعتمد",
                progress=snapshot.readiness_percent,
            ),
        )
        for index, card in enumerate(metrics):
            self.metric_host.addWidget(card, index // 2, index % 2)

    def _display_episode(self, episode: EpisodeRecord) -> None:
        self.active_episode_badge.findChild(QLabel).setText(
            f"الحلقة النشطة: {episode.title_ar}"
        )
        self.shot_count_badge.findChild(QLabel).setText(
            f"{episode.shot_count} لقطة"
        )
        self.model_badge.findChild(QLabel).setText(
            f"{episode.model}"
        )
        self.hero_status_badge.findChild(QLabel).setText(
            f"الحالة: {episode.stage_label_ar}"
        )
        preview_label = (
            "فيديو نهائي جاهز للمراجعة"
            if episode.final_video_path
            else "ستظهر معاينة الفيديو هنا بعد التوليد"
        )
        self.preview.set_context(preview_label, episode.current_shot_id)
        self.detail_labels["episode"].setText(episode.episode_id)
        self.detail_labels["shot"].setText(episode.current_shot_id)
        self.detail_labels["model"].setText(episode.model)
        self.detail_labels["provider"].setText(episode.provider)
        self.detail_labels["shots"].setText(
            f"{episode.approved_shot_count} / {episode.shot_count}"
        )
        safety = "مفعّلة" if episode.manifest_path else "غير مرتبطة"
        self.detail_labels["safety"].setText(safety)

    def _episode_action(self, episode: EpisodeRecord) -> None:
        if episode.conversion_ready:
            QMessageBox.information(
                self,
                "بوابة تحويل الفيديو",
                "واجهة التنفيذ أصبحت جاهزة، لكن ربط Runware والتنفيذ المدفوع "
                "سيتم في المرحلة التالية بعد تثبيت بوابة الاعتماد.",
            )
            self._log(f"VIDEO_CONVERSION_GATE_OPENED {episode.episode_id}")
            return
        if episode.final_video_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(episode.final_video_path)))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(episode.project_path)))

    def _episode_selection_changed(self) -> None:
        selected = self.episode_table.selectedItems()
        if not selected:
            return
        episode_id = selected[0].data(Qt.ItemDataRole.UserRole)
        episode = self._episode_by_id(str(episode_id))
        if episode is not None:
            self._display_episode(episode)

    def _select_episode(self, index: int) -> None:
        episode_id = self.project_combo.itemData(index)
        episode = self._episode_by_id(str(episode_id)) if episode_id else None
        if episode is not None:
            self._display_episode(episode)
            for row in range(self.episode_table.rowCount()):
                item = self.episode_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == episode.episode_id:
                    self.episode_table.selectRow(row)
                    break

    def _episode_by_id(self, episode_id: str) -> EpisodeRecord | None:
        for episode in self.snapshot.episodes:
            if episode.episode_id == episode_id:
                return episode
        return None

    def _filter_episode_rows(self, text: str) -> None:
        needle = text.strip().casefold()
        for row in range(self.episode_table.rowCount()):
            item = self.episode_table.item(row, 0)
            haystack = item.text().casefold() if item else ""
            self.episode_table.setRowHidden(row, bool(needle and needle not in haystack))

    def _refresh(self) -> None:
        self._populate(build_dashboard_snapshot(self.repo_root))

    def _open_repo_root(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.repo_root)))

    def _show_placeholder(self, label: str) -> None:
        if "لوحة التحكم" in label:
            return
        QMessageBox.information(
            self,
            label.replace("▤", "").replace("▶", "").strip(),
            "هذا القسم مدرج في تصميم الواجهة وسيتم تفعيله تباعًا. "
            "النسخة الحالية تركز على لوحة التحكم والحلقات الجاهزة للتحويل.",
        )

    def _log(self, message: str) -> None:
        self.execution_log.appendPlainText(message)
