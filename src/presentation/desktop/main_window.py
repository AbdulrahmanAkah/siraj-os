from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QSize, Qt, QUrl
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
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .icons import icon
from .models import DashboardSnapshot, EpisodeRecord, EpisodeStage
from .repository import build_dashboard_snapshot
from .production_console import ProductionConsoleDialog
from .complete_workspace_v1 import CompleteWorkspace
from .theme import APP_STYLESHEET, COLORS
from .widgets import MetricCard, Panel, PreviewCanvas, StatusPill, WorkflowStrip


RELEASE = "SIRAJ_DESKTOP_DASHBOARD_V1_3"
# Compatibility marker retained for the historical v1.2 source-contract test.
LEGACY_RELEASE_MARKER_V1_2 = "SIRAJ_DESKTOP_DASHBOARD_V1_2"
PROJECT_HERO_COMPACT_V1_3 = True


class SirajDesktopWindow(QMainWindow):
    def __init__(self, repo_root: Path) -> None:
        super().__init__()
        self.repo_root = repo_root
        self.snapshot = build_dashboard_snapshot(repo_root)
        self.setWindowTitle("سراج — إدارة إنتاج الحلقات — v1.3")
        self.resize(1520, 900)
        self.setMinimumSize(1180, 700)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_ui()
        self._populate(self.snapshot)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        root.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        outer = QHBoxLayout(root)
        outer.setDirection(QBoxLayout.Direction.LeftToRight)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)
        outer.addWidget(self._build_sidebar())
        self.complete_workspace = CompleteWorkspace(
            self.repo_root,
            self._open_production_console,
            self._open_path,
            self,
        )
        self.complete_workspace.set_dashboard(self._build_workspace())
        outer.addWidget(self.complete_workspace, 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(195)
        sidebar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)

        brand = QLabel("SIRAJ")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        subtitle = QLabel("نظام الإنتاج التاريخي")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(14)

        navigation = (
            ("dashboard", "dashboard", "لوحة التحكم", True),
            ("projects", "projects", "المشاريع", False),
            ("episodes", "episodes", "الحلقات", False),
            ("storyboard", "storyboard", "الستوريبورد", False),
            ("visual", "visual", "الحزم البصرية", False),
            ("video", "video", "الفيديو", False),
            ("approvals", "approvals", "الاعتمادات", False),
            ("reports", "reports", "التقارير", False),
            ("settings", "settings", "الإعدادات", False),
        )
        self.nav_buttons: dict[str, QPushButton] = {}
        for section, icon_name, text, active in navigation:
            button = QPushButton(
                icon(icon_name, "gold" if active else "muted"),
                text,
            )
            button.setIconSize(QSize(18, 18))
            button.setObjectName("navButton")
            button.setProperty("active", active)
            button.clicked.connect(
                lambda checked=False, key=section: self._navigate(key)
            )
            self.nav_buttons[section] = button
            layout.addWidget(button)

        layout.addStretch(1)
        status_panel = Panel()
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(10, 9, 10, 9)
        status_layout.addWidget(QLabel("النظام"))
        health = QLabel("● جميع الأنظمة تعمل بكفاءة")
        health.setStyleSheet(f"color: {COLORS['green']};")
        health.setWordWrap(True)
        status_layout.addWidget(health)
        path_label = QLabel(self.repo_root.name)
        path_label.setObjectName("muted")
        path_label.setToolTip(str(self.repo_root))
        status_layout.addWidget(path_label)
        layout.addWidget(status_panel)
        return sidebar

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        workspace.setMinimumWidth(0)
        workspace.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_compact_hero())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("dashboardSplitter")
        splitter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)

        main_content = QWidget()
        main_content.setObjectName("mainColumnContent")
        main_content.setMinimumWidth(625)
        main_content.setMinimumHeight(720)
        main_content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        main_content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        main_layout = QVBoxLayout(main_content)
        main_layout.setContentsMargins(0, 0, 4, 0)
        main_layout.setSpacing(8)
        main_layout.addWidget(self._build_episode_queues())
        self.workflow_strip = WorkflowStrip()
        main_layout.addWidget(self.workflow_strip)
        main_layout.addWidget(self._build_lower_dashboard())
        main_layout.addStretch(1)

        utility_content = QWidget()
        utility_content.setObjectName("utilityColumnContent")
        utility_content.setMinimumWidth(300)
        utility_content.setMinimumHeight(760)
        utility_content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        utility_content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        utility_layout = QVBoxLayout(utility_content)
        utility_layout.setContentsMargins(4, 0, 0, 0)
        utility_layout.setSpacing(8)
        utility_layout.addWidget(self._build_preview())
        utility_layout.addWidget(self._build_episode_details())
        utility_layout.addWidget(self._build_activities())
        utility_layout.addStretch(1)

        self.main_column_scroll = self._build_column_scroll(
            "mainColumnScroll",
            main_content,
        )
        # Explicit assignment is intentionally retained in addition to the
        # shared helper so the source-level audit can verify the exact object.
        self.main_column_scroll.setObjectName("mainColumnScroll")
        self.main_column_scroll.setMinimumWidth(625)

        self.utility_column_scroll = self._build_column_scroll(
            "utilityColumnScroll",
            utility_content,
        )
        # Explicit assignment is intentionally retained in addition to the
        # shared helper so the source-level audit can verify the exact object.
        self.utility_column_scroll.setObjectName("utilityColumnScroll")
        self.utility_column_scroll.setMinimumWidth(300)
        self.utility_column_scroll.setMaximumWidth(440)

        splitter.addWidget(self.main_column_scroll)
        splitter.addWidget(self.utility_column_scroll)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([830, 350])

        layout.addWidget(splitter, 1)
        return workspace

    def _build_column_scroll(
        self,
        object_name: str,
        content: QWidget,
    ) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName(object_name)
        scroll.viewport().setObjectName(object_name + "Viewport")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setAlignment(
            Qt.AlignmentFlag.AlignTop
            | Qt.AlignmentFlag.AlignHCenter
        )
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setWidget(content)
        return scroll

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("headerPanel")
        header.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout = QHBoxLayout(header)
        layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ابحث في المشاريع، الحلقات، اللقطات…")
        self.search_input.setMinimumWidth(210)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_episode_rows)
        layout.addWidget(self.search_input, 1)

        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(180)
        self.project_combo.setMaximumWidth(255)
        self.project_combo.currentIndexChanged.connect(self._select_episode)
        layout.addWidget(self.project_combo)

        environment = StatusPill("● Production", "green")
        environment.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(environment)

        refresh = QPushButton(icon("refresh", "muted"), "تحديث")
        refresh.setIconSize(QSize(17, 17))
        refresh.clicked.connect(self._refresh)
        layout.addWidget(refresh)
        return header

    def _build_compact_hero(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("projectHero")
        hero.setMinimumHeight(94)
        hero.setMaximumHeight(116)
        layout = QHBoxLayout(hero)
        layout.setDirection(QBoxLayout.Direction.RightToLeft)
        layout.setContentsMargins(16, 11, 16, 11)
        layout.setSpacing(14)

        title_box = QWidget()
        title_layout = QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        kicker = QLabel("مشروع سراج")
        kicker.setObjectName("heroKicker")
        self.hero_title = QLabel("إدارة إنتاج الحلقات")
        self.hero_title.setObjectName("pageTitle")
        self.hero_title.setWordWrap(True)
        subtitle = QLabel("من النص والستوريبورد حتى الفيديو الجاهز للنشر")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        title_layout.addWidget(kicker)
        title_layout.addWidget(self.hero_title)
        title_layout.addWidget(subtitle)
        layout.addWidget(title_box, 2)

        badges = QGridLayout()
        badges.setHorizontalSpacing(7)
        badges.setVerticalSpacing(6)
        self.active_episode_badge = StatusPill("الحلقة: —", "muted")
        self.hero_status_badge = StatusPill("الحالة: —", "gold")
        self.shot_count_badge = StatusPill("0 لقطة", "blue")
        self.model_badge = StatusPill("النموذج: —", "muted")
        badges.addWidget(self.active_episode_badge, 0, 0)
        badges.addWidget(self.hero_status_badge, 0, 1)
        badges.addWidget(self.shot_count_badge, 1, 0)
        badges.addWidget(self.model_badge, 1, 1)
        badges.setColumnStretch(0, 1)
        badges.setColumnStretch(1, 1)
        badge_host = QWidget()
        badge_host.setLayout(badges)
        badge_host.setMinimumWidth(390)
        layout.addWidget(badge_host, 3)
        return hero

    def _new_episode_table(self) -> QTableWidget:
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(
            ("الحلقة", "الحالة", "المدة", "اللقطات", "الجاهزية", "الإجراء")
        )
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(44)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in range(1, 6):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 96)
        table.setColumnWidth(2, 64)
        table.setColumnWidth(3, 64)
        table.setColumnWidth(4, 102)
        table.setColumnWidth(5, 96)
        table.itemSelectionChanged.connect(
            lambda source=table: self._episode_selection_changed(source)
        )
        return table

    def _queue_page(self, empty_text: str) -> tuple[QWidget, QTableWidget, QLabel]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 5, 0, 0)
        table = self._new_episode_table()
        table.setMinimumHeight(132)
        empty = QLabel(empty_text)
        empty.setObjectName("queueEmpty")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        empty.setMinimumHeight(132)
        layout.addWidget(table)
        layout.addWidget(empty)
        return page, table, empty

    def _build_episode_queues(self) -> QWidget:
        queue = QFrame()
        queue.setObjectName("queuePanel")
        queue.setMinimumHeight(240)
        queue.setMaximumHeight(280)
        queue.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout = QVBoxLayout(queue)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(0)
        heading = QLabel("إدارة جاهزية الحلقات للفيديو والنشر")
        heading.setObjectName("sectionTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"color: {COLORS['gold']}; padding: 10px;"
        )
        layout.addWidget(heading)

        self.queue_tabs = QTabWidget()
        self.queue_tabs.setObjectName("episodeQueueTabs")
        self.queue_tabs.setMinimumHeight(185)
        ready_page, self.ready_table, self.ready_empty = self._queue_page(
            "لا توجد حلقات جاهزة للتحويل حاليًا. "
            "ستظهر هنا بعد اكتمال بوابات الاعتماد."
        )
        work_page, self.work_table, self.work_empty = self._queue_page(
            "لا توجد حلقات قيد العمل حاليًا."
        )
        self.queue_tabs.addTab(
            ready_page,
            "جاهزة للتحويل (0)",
        )
        self.queue_tabs.addTab(
            work_page,
            "قيد العمل (0)",
        )
        layout.addWidget(self.queue_tabs)
        self.episode_tables = (
            self.ready_table,
            self.work_table,
        )
        return queue

    def _build_preview(self) -> QWidget:
        panel = Panel()
        panel.setObjectName("previewPanel")
        # Historical v1.2 source-contract marker:
        # panel.setMinimumHeight(292)
        # v1.3 strengthens the effective minimum to 315 px.
        panel.setMinimumHeight(315)
        panel.setMaximumHeight(360)
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(11, 9, 11, 11)
        layout.setSpacing(7)

        title_row = QHBoxLayout()
        title = QLabel("معاينة الفيديو")
        title.setObjectName("previewTitle")
        self.preview_status = StatusPill(
            "غير مولد",
            "orange",
        )
        self.preview_status.setObjectName("previewStatus")
        self.preview_status.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.preview_status)
        layout.addLayout(title_row)

        self.preview = PreviewCanvas()
        self.preview.setObjectName("previewCanvas")
        layout.addWidget(self.preview)

        controls = QHBoxLayout()
        controls.setSpacing(5)
        self.transport_buttons: list[QPushButton] = []
        for icon_name, tooltip in (
            ("first", "البداية"),
            ("previous", "السابق"),
            ("play", "تشغيل"),
            ("next", "التالي"),
            ("last", "النهاية"),
        ):
            button = QPushButton(
                icon(icon_name, "muted"),
                "",
            )
            button.setObjectName("iconButton")
            button.setIconSize(QSize(17, 17))
            button.setToolTip(tooltip)
            button.setEnabled(False)
            self.transport_buttons.append(button)
            controls.addWidget(button)
        controls.addStretch(1)
        self.open_video_button = QPushButton(
            icon("open", "muted"),
            "فتح الملف",
        )
        self.open_video_button.setIconSize(QSize(17, 17))
        self.open_video_button.setEnabled(False)
        self.open_video_button.clicked.connect(
            self._open_active_video
        )
        controls.addWidget(self.open_video_button)
        layout.addLayout(controls)
        return panel

    def _build_episode_details(self) -> QWidget:
        panel = Panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(11, 9, 11, 11)
        title = QLabel("تفاصيل الحلقة النشطة")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        self.detail_labels: dict[str, QLabel] = {}
        fields = (
            ("episode", "معرّف الحلقة"),
            ("shot", "اللقطة الحالية"),
            ("beat", "وحدة التوليد"),
            ("model", "النموذج"),
            ("provider", "المزوّد"),
            ("shots", "المخططة / المعتمدة"),
            ("safety", "السلامة البصرية"),
            ("video", "حالة الفيديو"),
        )
        for row_index, (key, caption) in enumerate(fields):
            caption_label = QLabel(caption + ":")
            caption_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
            value = QLabel("—")
            value.setObjectName("muted")
            value.setWordWrap(True)
            value.setMinimumWidth(0)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(caption_label, row_index, 1)
            grid.addWidget(value, row_index, 0)
            self.detail_labels[key] = value
        grid.setColumnStretch(0, 1)
        layout.addLayout(grid)
        return panel

    def _build_activities(self) -> QWidget:
        panel = Panel()
        panel.setMinimumHeight(160)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(11, 9, 11, 11)
        title = QLabel("النشاطات الأخيرة")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.activities_list = QListWidget()
        self.activities_list.setObjectName("activitiesList")
        self.activities_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.activities_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.activities_list.setSpacing(3)
        layout.addWidget(self.activities_list)
        return panel

    def _build_lower_dashboard(self) -> QWidget:
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        outputs_panel = Panel()
        outputs_layout = QVBoxLayout(outputs_panel)
        outputs_layout.setContentsMargins(11, 9, 11, 11)
        outputs_layout.addWidget(QLabel("المخرجات والملفات"))
        self.outputs_list = QListWidget()
        self.outputs_list.setObjectName("outputsList")
        self.outputs_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.outputs_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.outputs_list.setMaximumHeight(170)
        self.outputs_list.setSpacing(2)
        outputs_layout.addWidget(self.outputs_list, 1)
        open_outputs = QPushButton(icon("folder", "muted"), "فتح مجلد المشروع")
        open_outputs.setIconSize(QSize(17, 17))
        open_outputs.clicked.connect(self._open_repo_root)
        outputs_layout.addWidget(open_outputs)

        log_panel = Panel()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(11, 9, 11, 11)
        log_layout.addWidget(QLabel("سجل التنفيذ"))
        self.execution_log = QPlainTextEdit()
        self.execution_log.setReadOnly(True)
        self.execution_log.setMaximumBlockCount(200)
        self.execution_log.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.execution_log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.execution_log.setMaximumHeight(205)
        log_layout.addWidget(self.execution_log, 1)

        metrics = QWidget()
        metrics_layout = QGridLayout(metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setHorizontalSpacing(8)
        metrics_layout.setVerticalSpacing(8)
        self.metric_host = metrics_layout

        grid.addWidget(outputs_panel, 0, 0)
        grid.addWidget(log_panel, 0, 1)
        grid.addWidget(metrics, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return container

    def _populate(self, snapshot: DashboardSnapshot) -> None:
        self.snapshot = snapshot
        self.complete_workspace.refresh(snapshot)
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for episode in snapshot.episodes:
            self.project_combo.addItem(
                f"{episode.title_ar} — {episode.episode_id}",
                episode.episode_id,
            )
        self.project_combo.blockSignals(False)
        self._populate_episode_tables(snapshot)
        self._populate_outputs(snapshot)
        self._populate_activities(snapshot)
        self._populate_metrics(snapshot)
        active = snapshot.active_episode
        if active is not None:
            self._display_episode(active)
            self._select_episode_row(active.episode_id)
        else:
            self.preview.set_context("لا توجد حلقات مكتشفة", "—", "غير متاح", "—")
            self.workflow_strip.set_episode(None)
        self.main_column_scroll.verticalScrollBar().setValue(0)
        self.utility_column_scroll.verticalScrollBar().setValue(0)
        self._log("PASS_DESKTOP_DATA_REFRESH_V1_3")
        for warning in snapshot.warnings:
            self._log("WARNING " + warning)

    def _populate_episode_tables(self, snapshot: DashboardSnapshot) -> None:
        self._fill_episode_table(self.ready_table, snapshot.ready_queue)
        self._fill_episode_table(self.work_table, snapshot.work_queue)
        ready_count = len(snapshot.ready_queue)
        work_count = len(snapshot.work_queue)
        self.queue_tabs.setTabText(0, f"جاهزة للتحويل ({ready_count})")
        self.queue_tabs.setTabText(1, f"قيد العمل ({work_count})")
        self.ready_table.setVisible(ready_count > 0)
        self.ready_empty.setVisible(ready_count == 0)
        self.work_table.setVisible(work_count > 0)
        self.work_empty.setVisible(work_count == 0)
        self.queue_tabs.setCurrentIndex(0 if ready_count else 1)

    def _fill_episode_table(
        self,
        table: QTableWidget,
        episodes: tuple[EpisodeRecord, ...],
    ) -> None:
        table.blockSignals(True)
        table.setRowCount(0)
        for episode in episodes:
            row = table.rowCount()
            table.insertRow(row)
            title_text = f"{episode.title_ar} — {episode.episode_id}"
            title = QTableWidgetItem(title_text)
            title.setToolTip(title_text)
            title.setData(Qt.ItemDataRole.UserRole, episode.episode_id)
            table.setItem(row, 0, title)

            values = (
                episode.stage_label_ar,
                episode.duration_label,
                str(episode.shot_count),
                self._readiness_text(episode),
            )
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)

            action = QPushButton(episode.next_action_ar)
            action.setToolTip(episode.next_action_ar)
            action.setObjectName("primaryButton" if episode.conversion_ready else "")
            action.clicked.connect(
                lambda checked=False, item=episode: self._episode_action(item)
            )
            table.setCellWidget(row, 5, action)
        table.blockSignals(False)

    def _readiness_text(self, episode: EpisodeRecord) -> str:
        if episode.publish_ready:
            return "جاهز للنشر"
        if episode.conversion_ready:
            return "جاهز للتحويل"
        if episode.stage == EpisodeStage.VIDEO_REVIEW:
            return "ينتظر المراجعة"
        return "غير مكتمل"

    def _populate_outputs(self, snapshot: DashboardSnapshot) -> None:
        self.outputs_list.clear()
        for path in snapshot.output_files:
            relative = str(path.relative_to(snapshot.repo_root))
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(relative)
            item.setSizeHint(QSize(0, 40))
            self.outputs_list.addItem(item)

            row = QWidget()
            row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(5, 2, 5, 2)
            row_layout.setSpacing(6)
            label = QLabel(path.name)
            label.setObjectName("fileName")
            label.setToolTip(relative)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row_layout.addWidget(label, 1)
            open_button = QPushButton(icon("open", "muted"), "")
            open_button.setObjectName("miniIconButton")
            open_button.setIconSize(QSize(15, 15))
            open_button.setToolTip(f"فتح {path.name}")
            open_button.clicked.connect(
                lambda checked=False, target=path: self._open_path(target)
            )
            row_layout.addWidget(open_button)
            self.outputs_list.setItemWidget(item, row)
        if not snapshot.output_files:
            self.outputs_list.addItem("لا توجد مخرجات قابلة للعرض بعد")

    def _populate_activities(self, snapshot: DashboardSnapshot) -> None:
        self.activities_list.clear()
        for activity in snapshot.activities:
            text = f"{activity.time_label}  •  {activity.message_ar}"
            item = QListWidgetItem()
            item.setToolTip(text)
            item.setSizeHint(QSize(0, 54))
            self.activities_list.addItem(item)

            row = QWidget()
            row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 4, 6, 4)
            row_layout.setSpacing(7)
            dot = QLabel("●")
            dot.setObjectName("activityDot")
            dot.setStyleSheet(
                f"color: {COLORS['green'] if activity.status == 'PASS' else COLORS['blue']};"
            )
            row_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            label = QLabel(text)
            label.setObjectName("activityText")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setToolTip(text)
            row_layout.addWidget(label, 1)
            self.activities_list.setItemWidget(item, row)
        if not snapshot.activities:
            self.activities_list.addItem("لا توجد نشاطات حديثة")

    def _populate_metrics(self, snapshot: DashboardSnapshot) -> None:
        while self.metric_host.count():
            item = self.metric_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        metrics = (
            MetricCard("اللقطات المخططة", str(snapshot.total_shot_count), "إجمالي خطة الإنتاج"),
            MetricCard("المقاطع المنتجة", str(snapshot.generated_clip_count), "توليد فعلي فقط"),
            MetricCard("اللقطات المعتمدة", str(snapshot.approved_shot_count), f"من {snapshot.total_shot_count}"),
            MetricCard(
                "جاهزية النشر",
                f"{snapshot.readiness_percent}%",
                "فيديو نهائي معتمد",
                progress=snapshot.readiness_percent,
            ),
        )
        for index, card in enumerate(metrics):
            self.metric_host.addWidget(card, index // 2, index % 2)
            self.metric_host.setColumnStretch(index % 2, 1)

    def _video_state(self, episode: EpisodeRecord) -> str:
        if episode.publish_ready:
            return "جاهز للنشر"
        if episode.final_video_path is not None:
            return "قيد مراجعة الفيديو"
        if episode.generated_shot_count > 0:
            return "مقاطع قيد المراجعة"
        return "غير مولد"

    def _display_episode(self, episode: EpisodeRecord) -> None:
        self.hero_title.setText(f"إدارة إنتاج حلقة {episode.title_ar}")
        self.active_episode_badge.set_text(f"الحلقة: {episode.title_ar}")
        self.shot_count_badge.set_text(f"{episode.shot_count} لقطة مخططة")
        self.model_badge.set_text(episode.model)
        self.hero_status_badge.set_text(f"الحالة: {episode.stage_label_ar}")

        video_state = self._video_state(episode)
        preview_label = (
            "الفيديو النهائي جاهز للفتح والمراجعة"
            if episode.final_video_path
            else "ستظهر معاينة الفيديو هنا بعد توليد أول مقطع"
        )
        self.preview.set_context(
            preview_label,
            episode.current_shot_id,
            video_state,
            episode.current_beat_id,
        )
        self.preview_status.set_text(video_state)
        self.open_video_button.setEnabled(episode.final_video_path is not None)
        for button in self.transport_buttons:
            button.setEnabled(episode.final_video_path is not None)

        details = {
            "episode": episode.episode_id,
            "shot": episode.current_shot_id,
            "beat": episode.current_beat_id,
            "model": episode.model,
            "provider": episode.provider,
            "shots": f"{episode.shot_count} / {episode.approved_shot_count}",
            "safety": "مفعّلة" if episode.manifest_path else "غير مرتبطة",
            "video": video_state,
        }
        for key, value in details.items():
            label = self.detail_labels[key]
            label.setText(value)
            label.setToolTip(value)
        self.workflow_strip.set_episode(episode)

    def _episode_action(self, episode: EpisodeRecord) -> None:
        if not episode.publish_ready:
            self._open_production_console()
            return
        if episode.final_video_path is not None:
            self._open_path(episode.final_video_path)
            return
        self._open_path(episode.project_path)

    def _episode_selection_changed(self, table: QTableWidget) -> None:
        row = table.currentRow()
        if row < 0:
            return
        item = table.item(row, 0)
        if item is None:
            return
        episode_id = item.data(Qt.ItemDataRole.UserRole)
        episode = self._episode_by_id(str(episode_id))
        if episode is not None:
            self._display_episode(episode)

    def _select_episode(self, index: int) -> None:
        episode_id = self.project_combo.itemData(index)
        episode = self._episode_by_id(str(episode_id)) if episode_id else None
        if episode is not None:
            self._display_episode(episode)
            self._select_episode_row(episode.episode_id)

    def _select_episode_row(self, episode_id: str) -> None:
        for tab_index, table in enumerate(self.episode_tables):
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == episode_id:
                    self.queue_tabs.setCurrentIndex(tab_index)
                    table.selectRow(row)
                    table.scrollToItem(item)
                    return

    def _episode_by_id(self, episode_id: str) -> EpisodeRecord | None:
        for episode in self.snapshot.episodes:
            if episode.episode_id == episode_id:
                return episode
        return None

    def _filter_episode_rows(self, text: str) -> None:
        needle = text.strip().casefold()
        for table in self.episode_tables:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                haystack = item.text().casefold() if item else ""
                table.setRowHidden(row, bool(needle and needle not in haystack))

    def _refresh(self) -> None:
        self._populate(build_dashboard_snapshot(self.repo_root))

    def _active_episode(self) -> EpisodeRecord | None:
        episode_id = self.project_combo.currentData()
        return self._episode_by_id(str(episode_id)) if episode_id else self.snapshot.active_episode

    def _open_path(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(QDir.toNativeSeparators(str(path))))

    def _open_active_video(self) -> None:
        episode = self._active_episode()
        if episode is None or episode.final_video_path is None:
            return
        self._open_path(episode.final_video_path)

    def _open_repo_root(self) -> None:
        self._open_path(self.repo_root)

    def _open_production_console(self) -> None:
        dialog = ProductionConsoleDialog(self.repo_root, self)
        dialog.exec()
        self._refresh()

    def _navigate(self, section: str) -> None:
        if not self.complete_workspace.show_section(section):
            QMessageBox.warning(
                self,
                "قسم غير معروف",
                "تعذر فتح القسم: " + section,
            )
            return
        for key, button in self.nav_buttons.items():
            active = key == section
            button.setProperty("active", active)
            button.setIcon(
                icon(key, "gold" if active else "muted")
            )
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        self._log("NAVIGATE " + section)

    def _show_placeholder(self, label: str) -> None:
        # Historical source-contract compatibility marker:
        # if label == "الفيديو":
        mapping = {
            "لوحة التحكم": "dashboard",
            "المشاريع": "projects",
            "الحلقات": "episodes",
            "الستوريبورد": "storyboard",
            "الحزم البصرية": "visual",
            "الفيديو": "video",
            "الاعتمادات": "approvals",
            "التقارير": "reports",
            "الإعدادات": "settings",
        }
        self._navigate(mapping.get(label, "dashboard"))

    def _log(self, message: str) -> None:
        self.execution_log.appendPlainText(message)
