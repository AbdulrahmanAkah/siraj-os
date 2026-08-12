"""SIRAJ Production Studio V6.0.1 — resume-aware Autopilot UI."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from src.presentation.desktop.production_studio_v5_4_4 import (
    ProductionStudioWindow,
)
from src.application.siraj_series_autopilot_v6_0_1 import (
    COMPAT_REL,
    audit_backend_compatibility,
    resolve_resume_state,
    stage_graph,
)


class ProductionStudioV601Window(ProductionStudioWindow):
    def __init__(self, repo_root: Path):
        super().__init__(repo_root)
        self.setWindowTitle("سراج — Production Studio V6.0.1 Autopilot")

        self.autopilot_page = self._build_autopilot_page()
        self.stack.insertWidget(0, self.autopilot_page)

        item = QListWidgetItem("التشغيل التلقائي الكامل")
        item.setData(Qt.ItemDataRole.UserRole, "autopilot")
        self.sidebar.insertItem(0, item)

        self.sidebar.setCurrentRow(0)
        self.refresh_autopilot()

    def _build_autopilot_page(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        title = QLabel("Autopilot — إنتاج الحلقة كاملة")
        title.setObjectName("EpisodeTitle")
        root.addWidget(title)

        self.resume_banner = QLabel()
        self.resume_banner.setWordWrap(True)
        root.addWidget(self.resume_banner)

        self.autopilot_status = QLabel()
        self.autopilot_status.setWordWrap(True)
        root.addWidget(self.autopilot_status)

        self.autopilot_button = QPushButton()
        self.autopilot_button.setObjectName("PrimaryButton")
        self.autopilot_button.clicked.connect(self._start_autopilot)
        root.addWidget(self.autopilot_button)

        self.reaudit_button = QPushButton("إعادة فحص جاهزية المسار الكامل")
        self.reaudit_button.clicked.connect(self._reaudit)
        root.addWidget(self.reaudit_button)

        self.stage_table = QTableWidget(0, 5)
        self.stage_table.setHorizontalHeaderLabels(
            ["#", "المرحلة", "الحلقة 002", "النوع", "Backend"]
        )
        self.stage_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.stage_table.verticalHeader().setVisible(False)
        header = self.stage_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.stage_table, 1)

        return page

    def _reaudit(self):
        try:
            audit_backend_compatibility(self.repo_root)
        except Exception as exc:
            QMessageBox.critical(self, "فشل الفحص", str(exc))
            return
        self.refresh_autopilot()

    def refresh_autopilot(self):
        try:
            report = audit_backend_compatibility(self.repo_root)
            resume = resolve_resume_state(self.repo_root)
        except Exception as exc:
            self.resume_banner.setText("تعذر تحديد نقطة الاستئناف: " + str(exc))
            self.autopilot_button.setEnabled(False)
            return

        if resume.mode == "RESUME_EXISTING_EPISODE":
            self.resume_banner.setObjectName("StatusBadgeGood")
            self.resume_banner.setText(
                "الحلقة الحالية: 002\n"
                f"الاستئناف الإجباري: {resume.resume_stage}\n"
                "جميع المراحل السابقة مكتملة ومحمية من إعادة التشغيل.\n"
                "لن يعيد سراج البحث أو المصادر أو السيناريو أو التشكيل لهذه الحلقة."
            )
            self.autopilot_button.setText(
                f"استأنف الحلقة 002 من {resume.resume_stage}"
            )
        else:
            self.resume_banner.setObjectName("StatusBadge")
            self.resume_banner.setText(
                "لا توجد حلقة غير مكتملة. الحلقة الجديدة ستبدأ من TOPIC_SELECTION."
            )
            self.autopilot_button.setText("ابدأ حلقة جديدة بالكامل")

        current_locked = bool(report["current_episode_start_locked"])
        future_locked = bool(report["future_new_episode_start_locked"])

        if current_locked:
            self.autopilot_status.setObjectName("StatusBadgeWarn")
            self.autopilot_status.setText(
                "الحلقة 002 لن تبدأ بعد حتى نعتمد كل Backends المطلوبة "
                f"من {resume.resume_stage} حتى المراجعة البشرية.\n"
                f"المتبقي للحلقة الحالية: {report['current_episode_uncertified_stage_count']} مرحلة.\n"
                f"المتبقي لمسار الحلقات الجديدة الكامل: "
                f"{report['future_full_pipeline_uncertified_stage_count']} مرحلة."
            )
            self.autopilot_button.setEnabled(False)
        else:
            self.autopilot_status.setObjectName("StatusBadgeGood")
            self.autopilot_status.setText(
                "المسار المتبقي للحلقة الحالية معتمد ويمكن استئنافه بدون إعادة ما سبق."
            )
            self.autopilot_button.setEnabled(True)

        graph = stage_graph()
        info_map = report["stages"]
        self.stage_table.setRowCount(len(graph))

        for row, stage in enumerate(graph):
            name = stage["stage"]
            info = info_map.get(name, {})
            if name in resume.completed_stages:
                episode_state = "مكتمل — محمي"
            elif name == resume.resume_stage:
                episode_state = "نقطة الاستئناف"
            elif name == "READY_FOR_FINAL_HUMAN_REVIEW":
                episode_state = "الهدف النهائي"
            else:
                episode_state = "لاحق"

            if name == "READY_FOR_FINAL_HUMAN_REVIEW":
                backend = "Human Gate"
            else:
                backend = (
                    "معتمد"
                    if info.get("certified") is True
                    else info.get("certification", "غير معتمد")
                )

            values = [
                str(stage["index"]),
                name,
                episode_state,
                stage["kind"],
                backend,
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col in {0, 2, 3, 4}:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.stage_table.setItem(row, col, cell)

    def _start_autopilot(self):
        QMessageBox.information(
            self,
            "Autopilot",
            "تم تثبيت منطق الاستئناف والحماية. التنفيذ الكامل سيُفتح فقط "
            "بعد اعتماد Backends المتبقية، حتى لا ندفع في مرحلة ثم نتوقف "
            "بسبب مرحلة لاحقة غير مربوطة.",
        )


def launch_production_studio_v6_0_1(repo_root: Path) -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("SIRAJ Production Studio V6.0.1")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    window = ProductionStudioV601Window(repo_root.resolve())
    window.show()
    return app.exec()
