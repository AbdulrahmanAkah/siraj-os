"""Canonical Desktop operator surface for next-episode manual visuals."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.application.canonical_manual_visual_profile_v1 import PROFILE_REL
from src.application.canonical_next_episode_manual_visual_pipeline_v1 import (
    CanonicalManualVisualPipelineError,
    archive_episode,
    assemble_manual_visual_episode,
    bootstrap_episode,
    build_master,
    certify_shorts_compatibility,
    export_manual_visual_handoff,
    import_manual_visuals,
    lock_imported_visuals,
    record_human_final_review,
    run_separated_qa,
    workflow_status,
)
from src.application.manual_visual_asset_ingest_v1 import record_human_asset_selection


class ManualVisualPipelineDock(QDockWidget):
    def __init__(self, repo_root: Path, parent: QWidget | None = None) -> None:
        super().__init__("مسار الحلقة الجديدة — إنتاج مرئي يدوي", parent)
        self.repo_root = Path(repo_root).resolve()
        self.setObjectName("canonicalManualVisualPipelineDockV1")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setDirection(QVBoxLayout.Direction.TopToBottom)
        notice = QLabel("الإنتاج المرئي آليًا أو عبر مزود مدفوع معطل في هذا المسار. صدّر الحزمة، أنشئ المرئيات يدويًا، ثم أعد استيرادها.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        row = QHBoxLayout()
        self.episode_combo = QComboBox()
        self.episode_combo.currentIndexChanged.connect(self.refresh)
        new_button = QPushButton("حلقة جديدة")
        new_button.clicked.connect(self._new_episode)
        row.addWidget(self.episode_combo, 1)
        row.addWidget(new_button)
        layout.addLayout(row)
        self.stage_label = QLabel("لا توجد حلقة محددة")
        self.stage_label.setWordWrap(True)
        layout.addWidget(self.stage_label)
        form = QFormLayout()
        self.ingest_path = QLineEdit()
        choose = QPushButton("اختيار مجلد المرئيات")
        choose.clicked.connect(self._choose_ingest)
        form.addRow(choose, self.ingest_path)
        layout.addLayout(form)
        actions = (
            ("تصدير حزمة الإنتاج المرئي", self._export),
            ("استيراد المرئيات والتحقق منها", self._import),
            ("قفل المرئيات المقبولة", self._lock),
            ("استكمال التجميع والمونتاج", self._assemble),
            ("تشغيل مراحل الجودة المنفصلة", self._qa),
            ("المراجعة البشرية النهائية", self._human_review),
            ("بناء الماستر", self._master),
            ("اعتماد توافق المقاطع القصيرة", self._shorts),
            ("أرشفة الحلقة", self._archive),
        )
        for label, callback in actions:
            button = QPushButton(label)
            button.clicked.connect(callback)
            layout.addWidget(button)
        refresh = QPushButton("تحديث الحالة")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        layout.addStretch(1)
        self.setWidget(body)
        self._reload_episodes()

    def _reload_episodes(self, preferred: str | None = None) -> None:
        current = preferred or self.episode_combo.currentData()
        self.episode_combo.blockSignals(True)
        self.episode_combo.clear()
        projects = self.repo_root / "projects"
        if projects.is_dir():
            for profile in sorted(projects.glob(f"*/{PROFILE_REL.as_posix()}")):
                episode_id = profile.parent.parent.name
                self.episode_combo.addItem(episode_id, episode_id)
        if current:
            index = self.episode_combo.findData(current)
            if index >= 0:
                self.episode_combo.setCurrentIndex(index)
        self.episode_combo.blockSignals(False)
        self.refresh()

    def select_episode(self, episode_id: str) -> None:
        self._reload_episodes(episode_id)
        self.show()
        self.raise_()

    def _episode(self) -> str:
        value = str(self.episode_combo.currentData() or "").strip()
        if not value:
            raise CanonicalManualVisualPipelineError("اختر حلقة أولًا")
        return value

    def _invoke(self, callback) -> None:
        try:
            result = callback()
        except Exception as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            self.refresh()
            return
        QMessageBox.information(self, "SIRAJ", str(result.get("status") or "تم"))
        self.refresh()

    def _new_episode(self) -> None:
        episode_id, accepted = QInputDialog.getText(self, "حلقة جديدة", "معرف الحلقة:")
        if not accepted or not episode_id.strip():
            return
        self._invoke(lambda: bootstrap_episode(self.repo_root, episode_id.strip()))
        self._reload_episodes(episode_id.strip())

    def _choose_ingest(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "اختر مجلد المرئيات اليدوية")
        if path:
            self.ingest_path.setText(path)

    def _export(self) -> None:
        self._invoke(lambda: export_manual_visual_handoff(self.repo_root, self._episode()))

    def _import(self) -> None:
        path = Path(self.ingest_path.text().strip())
        actor, accepted = QInputDialog.getText(self, "اعتماد المرئيات اليدوية", "اسم الشخص الذي اختار المرئيات وراجع القيود الدستورية:")
        if not accepted or not actor.strip():
            return
        confirmation = QMessageBox.question(
            self,
            "تأكيد بشري",
            "هل تؤكد أن كل ملف مختار يطابق اللقطة ولا يخالف قواعد الوجوه والستر والحقبة والنص؟",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        episode_root = self.repo_root / "projects" / self._episode()
        template = episode_root / "manual-visuals" / "handoff-v1" / "manual-visual-ingest-template-v1.json"
        try:
            record_human_asset_selection(
                ingest_template_path=template,
                ingest_dir=path,
                human_actor=actor.strip(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "SIRAJ", str(exc))
            return
        self._invoke(lambda: import_manual_visuals(self.repo_root, self._episode(), ingest_dir=path))

    def _lock(self) -> None:
        self._invoke(lambda: lock_imported_visuals(self.repo_root, self._episode()))

    def _assemble(self) -> None:
        self._invoke(lambda: assemble_manual_visual_episode(self.repo_root, self._episode()))

    def _qa(self) -> None:
        self._invoke(lambda: run_separated_qa(self.repo_root, self._episode()))

    def _human_review(self) -> None:
        actor, accepted = QInputDialog.getText(self, "المراجعة النهائية", "اسم المراجع البشري بعد مشاهدة الحلقة كاملة:")
        if not accepted or not actor.strip():
            return
        answer = QMessageBox.question(self, "اعتماد نهائي", "هل تعتمد النسخة المرئية والصوتية الحالية اعتمادًا نهائيًا؟")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._invoke(lambda: record_human_final_review(self.repo_root, self._episode(), human_actor=actor.strip(), decision="APPROVED"))

    def _master(self) -> None:
        self._invoke(lambda: build_master(self.repo_root, self._episode()))

    def _shorts(self) -> None:
        self._invoke(lambda: certify_shorts_compatibility(self.repo_root, self._episode()))

    def _archive(self) -> None:
        self._invoke(lambda: archive_episode(self.repo_root, self._episode()))

    def refresh(self) -> None:
        try:
            status = workflow_status(self.repo_root, self._episode())
        except Exception:
            self.stage_label.setText("لا توجد حلقة يدوية محددة")
            return
        actions = "، ".join(status["available_actions"]) or "لا إجراء آلي مطلوب"
        self.stage_label.setText(f"المرحلة الحالية: {status['stage']}\nالإجراء التالي: {actions}")


def install_manual_visual_pipeline_dock(window) -> ManualVisualPipelineDock:
    dock = ManualVisualPipelineDock(window.repo_root, window)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    window.manual_visual_pipeline_dock = dock
    dock.hide()
    return dock


def focus_manual_visual_pipeline(window, episode_id: str | None = None) -> None:
    dock = getattr(window, "manual_visual_pipeline_dock", None)
    if dock is None:
        dock = install_manual_visual_pipeline_dock(window)
    if episode_id:
        dock.select_episode(episode_id)
    else:
        dock.show()
        dock.raise_()
