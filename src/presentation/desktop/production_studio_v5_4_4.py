"""Modern SIRAJ Production Studio V5.4.4 desktop interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
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
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.application.siraj_production_studio_controller_v5_4_4 import (
    EXPLICIT_CONFIRMATION_PHRASE,
    ProductionStudioError,
    authorize_final_tts,
    execute_one_authorized_item,
    load_dashboard_state,
    pending_authorized_queue_ids,
)


STYLE = """
QWidget {
    background: #0c1016;
    color: #e8eaf0;
    font-family: "Segoe UI", "Tahoma";
    font-size: 13px;
}
QMainWindow {
    background: #0c1016;
}
#TopBar {
    background: #111722;
    border-bottom: 1px solid #273041;
}
#Brand {
    color: #f1d28a;
    font-size: 24px;
    font-weight: 700;
}
#EpisodeTitle {
    color: #f6f7fb;
    font-size: 18px;
    font-weight: 650;
}
#Subtle {
    color: #8f9bae;
}
#StatusBadge {
    background: #172130;
    border: 1px solid #31415a;
    border-radius: 9px;
    padding: 5px 10px;
    color: #c8d2e2;
}
#StatusBadgeGood {
    background: #10261f;
    border: 1px solid #235b45;
    border-radius: 9px;
    padding: 5px 10px;
    color: #9fe0bf;
}
#StatusBadgeWarn {
    background: #2a2112;
    border: 1px solid #6a5120;
    border-radius: 9px;
    padding: 5px 10px;
    color: #f0d690;
}
#Sidebar {
    background: #0f141d;
    border-right: 1px solid #232c3a;
}
QListWidget {
    border: none;
    outline: none;
    background: transparent;
    padding: 10px;
}
QListWidget::item {
    padding: 12px 14px;
    margin: 3px 0px;
    border-radius: 8px;
    color: #99a5b6;
}
QListWidget::item:selected {
    background: #1a2330;
    color: #f1d28a;
}
QListWidget::item:hover {
    background: #151d28;
    color: #dce2ea;
}
#Card {
    background: #121923;
    border: 1px solid #263142;
    border-radius: 12px;
}
#CardTitle {
    color: #9aa7ba;
    font-size: 12px;
}
#CardValue {
    color: #f7f8fb;
    font-size: 22px;
    font-weight: 700;
}
#GoldValue {
    color: #f1d28a;
    font-size: 18px;
    font-weight: 700;
}
QPushButton {
    background: #1a2230;
    border: 1px solid #334156;
    border-radius: 8px;
    padding: 9px 15px;
    color: #e9edf5;
}
QPushButton:hover {
    background: #222d3d;
    border-color: #465a76;
}
QPushButton:pressed {
    background: #101722;
}
QPushButton:disabled {
    color: #5f6875;
    background: #121720;
    border-color: #202733;
}
#PrimaryButton {
    background: #c99c45;
    border-color: #dfb85f;
    color: #101319;
    font-weight: 700;
}
#PrimaryButton:hover {
    background: #dbad50;
}
#DangerButton {
    background: #2b1719;
    border-color: #673037;
    color: #efafb7;
}
QTableWidget {
    background: #10161f;
    alternate-background-color: #121a25;
    border: 1px solid #263142;
    border-radius: 10px;
    gridline-color: #222c3b;
    selection-background-color: #1f2a39;
    selection-color: #f7f8fb;
}
QHeaderView::section {
    background: #151d28;
    color: #aeb8c7;
    border: none;
    border-bottom: 1px solid #2c3748;
    padding: 8px;
    font-weight: 650;
}
QProgressBar {
    background: #111821;
    border: 1px solid #293547;
    border-radius: 7px;
    text-align: center;
    color: #d8dee8;
    min-height: 16px;
}
QProgressBar::chunk {
    background: #c99c45;
    border-radius: 6px;
}
QLineEdit, QTextEdit {
    background: #0f151e;
    border: 1px solid #2a3648;
    border-radius: 8px;
    padding: 8px;
    color: #eef1f6;
}
QLineEdit:focus, QTextEdit:focus {
    border-color: #c99c45;
}
"""


def _status_text(value: str) -> str:
    mapping = {
        "AWAITING_EXPLICIT_PAID_AUTHORIZATION": "بانتظار التفويض",
        "AUTHORIZED": "مصرّح",
        "SUBMISSION_LOCKED": "مقفول قبل الإرسال",
        "COMPLETE": "مكتمل",
        "IN_PROGRESS": "قيد التنفيذ",
        "PASS": "ناجح",
        "ACTIVE": "فعّال",
    }
    return mapping.get(value, value.replace("_", " "))


class FinalTtsWorker(QThread):
    progress_changed = Signal(int, int, str)
    item_completed = Signal(str, str)
    failed = Signal(str)
    finished_successfully = Signal()

    def __init__(self, repo_root: Path, parent=None):
        super().__init__(parent)
        self.repo_root = repo_root

    def run(self):
        try:
            queue_ids = pending_authorized_queue_ids(self.repo_root)
            total = len(queue_ids)
            for index, queue_id in enumerate(queue_ids, 1):
                self.progress_changed.emit(
                    index - 1,
                    total,
                    f"تنفيذ {queue_id}",
                )
                result = execute_one_authorized_item(
                    self.repo_root,
                    queue_id,
                )
                self.item_completed.emit(
                    queue_id,
                    result.status,
                )
                self.progress_changed.emit(
                    index,
                    total,
                    f"اكتمل {queue_id}",
                )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_successfully.emit()


class AuthorizationDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تفويض FINAL_TTS")
        self.setMinimumWidth(620)
        self.setModal(True)
        self.confirmed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        title = QLabel("تفويض إنتاج الصوت النهائي")
        title.setObjectName("EpisodeTitle")
        root.addWidget(title)

        details = QLabel(
            "سيتم استخدام الراوي المقفول وإعدادات الحلقة الأولى نفسها.\n"
            f"المزوّد: {state.provider}\n"
            f"النموذج: {state.model_id}\n"
            f"عدد الطلبات المخطط لها: {state.planned_requests}\n"
            f"إجمالي الأحرف: {state.total_characters:,}\n"
            "إعادة المحاولة التلقائية: ممنوعة\n"
            "أي فشل أو نتيجة مجهولة ستوقف التنفيذ وتحتاج تفويضًا جديدًا."
        )
        details.setWordWrap(True)
        details.setObjectName("Subtle")
        root.addWidget(details)

        if state.historical_reference_usd is not None:
            historical = QLabel(
                "مرجع الحلقة الأولى غير الملزم: "
                f"${state.historical_reference_usd:.6f} "
                "(ليس سعرًا حاليًا ولا سقفًا للتكلفة)"
            )
            historical.setObjectName("StatusBadgeWarn")
            historical.setWordWrap(True)
            root.addWidget(historical)

        instruction = QLabel(
            "لمنع التفويض العرضي، اكتب العبارة التالية حرفيًا:"
        )
        instruction.setObjectName("Subtle")
        root.addWidget(instruction)

        phrase = QLabel(EXPLICIT_CONFIRMATION_PHRASE)
        phrase.setObjectName("GoldValue")
        phrase.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(phrase)

        self.input = QLineEdit()
        self.input.setPlaceholderText("اكتب عبارة التفويض هنا")
        self.input.textChanged.connect(self._sync)
        root.addWidget(self.input)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("إلغاء")
        cancel.clicked.connect(self.reject)
        self.confirm = QPushButton("تفويض FINAL_TTS")
        self.confirm.setObjectName("PrimaryButton")
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self._accept)
        actions.addWidget(cancel)
        actions.addWidget(self.confirm)
        root.addLayout(actions)

    def _sync(self, value):
        self.confirm.setEnabled(
            value.strip() == EXPLICIT_CONFIRMATION_PHRASE
        )

    def _accept(self):
        self.confirmed = True
        self.accept()


class MetricCard(QFrame):
    def __init__(self, title: str, value: str, accent=False):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        v = QLabel(value)
        v.setObjectName("GoldValue" if accent else "CardValue")
        v.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(v)
        self.value_label = v

    def set_value(self, value: str):
        self.value_label.setText(value)


class ProductionStudioWindow(QMainWindow):
    def __init__(self, repo_root: Path):
        super().__init__()
        self.repo_root = repo_root.resolve()
        self.worker = None
        self.setWindowTitle("سراج — Production Studio V5")
        self.resize(1480, 900)
        self.setMinimumSize(1120, 720)
        self.setStyleSheet(STYLE)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(235)
        stages = [
            ("لوحة القيادة", "dashboard"),
            ("الصوت النهائي", "tts"),
            ("التوقيت والإيقاع", "timing"),
            ("الستوري بورد", "storyboard"),
            ("إنتاج الوسائط", "media"),
            ("المونتاج", "montage"),
            ("الجودة والإصلاح", "qa"),
            ("المراجعة والنشر", "publish"),
            ("السجل والتشخيص", "logs"),
        ]
        for label, key in stages:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self._change_page)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        self.dashboard_page = self._build_dashboard()
        self.tts_page = self._build_tts_page()
        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.tts_page)

        for stage_name in (
            "التوقيت والإيقاع",
            "الستوري بورد",
            "إنتاج الوسائط",
            "المونتاج",
            "الجودة والإصلاح",
            "المراجعة والنشر",
        ):
            self.stack.addWidget(
                self._build_future_stage_page(stage_name)
            )

        self.logs_page = self._build_logs_page()
        self.stack.addWidget(self.logs_page)

        self.sidebar.setCurrentRow(0)
        self.refresh_state()

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(22, 14, 22, 14)
        layout.setSpacing(12)

        brand = QLabel("سراج")
        brand.setObjectName("Brand")
        layout.addWidget(brand)

        divider = QLabel("•")
        divider.setObjectName("Subtle")
        layout.addWidget(divider)

        self.episode_label = QLabel(
            "الحلقة 002 — من الوسوسة إلى التوبة"
        )
        self.episode_label.setObjectName("EpisodeTitle")
        layout.addWidget(self.episode_label)

        layout.addStretch(1)

        self.top_stage_badge = QLabel("FINAL_TTS")
        self.top_stage_badge.setObjectName("StatusBadge")
        layout.addWidget(self.top_stage_badge)

        self.top_lock_badge = QLabel("الراوي: مقفول")
        self.top_lock_badge.setObjectName("StatusBadgeGood")
        layout.addWidget(self.top_lock_badge)

        self.refresh_button = QPushButton("تحديث")
        self.refresh_button.clicked.connect(self.refresh_state)
        layout.addWidget(self.refresh_button)

        return bar

    def _build_dashboard(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        title = QLabel("مركز الإنتاج")
        title.setObjectName("EpisodeTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "حالة الحلقة، بوابات الأمان، والمرحلة التنفيذية الحالية."
        )
        subtitle.setObjectName("Subtle")
        root.addWidget(subtitle)

        cards = QGridLayout()
        cards.setSpacing(12)
        self.card_stage = MetricCard("المرحلة الحالية", "FINAL_TTS", True)
        self.card_progress = MetricCard("تقدم FINAL_TTS", "0 / 0")
        self.card_requests = MetricCard("طلبات ElevenLabs", "0")
        self.card_chars = MetricCard("أحرف TTS", "0")
        self.card_pron = MetricCard("بوابة النطق", "—")
        self.card_auth = MetricCard("التفويض", "—")
        cards.addWidget(self.card_stage, 0, 0)
        cards.addWidget(self.card_progress, 0, 1)
        cards.addWidget(self.card_requests, 0, 2)
        cards.addWidget(self.card_chars, 1, 0)
        cards.addWidget(self.card_pron, 1, 1)
        cards.addWidget(self.card_auth, 1, 2)
        root.addLayout(cards)

        safety = QFrame()
        safety.setObjectName("Card")
        safety_layout = QVBoxLayout(safety)
        safety_layout.setContentsMargins(18, 16, 18, 16)
        safety_title = QLabel("بوابات الأمان الفعّالة")
        safety_title.setObjectName("EpisodeTitle")
        safety_layout.addWidget(safety_title)

        self.safety_text = QLabel()
        self.safety_text.setObjectName("Subtle")
        self.safety_text.setWordWrap(True)
        safety_layout.addWidget(self.safety_text)
        root.addWidget(safety)

        root.addStretch(1)
        return page

    def _build_tts_page(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        labels = QVBoxLayout()
        title = QLabel("FINAL_TTS — ElevenLabs")
        title.setObjectName("EpisodeTitle")
        labels.addWidget(title)
        self.tts_summary = QLabel()
        self.tts_summary.setObjectName("Subtle")
        labels.addWidget(self.tts_summary)
        header.addLayout(labels, 1)

        self.open_folder_button = QPushButton("فتح مجلد الصوت")
        self.open_folder_button.clicked.connect(self._open_audio_folder)
        header.addWidget(self.open_folder_button)

        self.authorize_button = QPushButton("تفويض الإنتاج المدفوع")
        self.authorize_button.setObjectName("PrimaryButton")
        self.authorize_button.clicked.connect(self._authorize)
        header.addWidget(self.authorize_button)

        self.execute_button = QPushButton("تنفيذ FINAL_TTS")
        self.execute_button.setObjectName("PrimaryButton")
        self.execute_button.clicked.connect(self._execute_tts)
        header.addWidget(self.execute_button)

        root.addLayout(header)

        self.tts_progress = QProgressBar()
        self.tts_progress.setRange(0, 100)
        root.addWidget(self.tts_progress)

        self.tts_status = QLabel()
        self.tts_status.setObjectName("StatusBadge")
        root.addWidget(self.tts_status)

        self.tts_table = QTableWidget(0, 7)
        self.tts_table.setHorizontalHeaderLabels(
            [
                "#",
                "المقطع",
                "الحالة",
                "الأحرف",
                "الوقفة",
                "المدة",
                "المخرج",
            ]
        )
        self.tts_table.setAlternatingRowColors(True)
        self.tts_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tts_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.tts_table.verticalHeader().setVisible(False)
        header_view = self.tts_table.horizontalHeader()
        header_view.setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        header_view.setSectionResizeMode(
            6,
            QHeaderView.ResizeMode.Stretch,
        )
        root.addWidget(self.tts_table, 1)

        return page

    def _build_future_stage_page(self, stage_name):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        title = QLabel(stage_name)
        title.setObjectName("EpisodeTitle")
        layout.addWidget(title)
        badge = QLabel("سيُفعّل تلقائيًا عند وصول خط الإنتاج إلى هذه المرحلة.")
        badge.setObjectName("StatusBadge")
        badge.setWordWrap(True)
        layout.addWidget(badge)
        note = QLabel(
            "تم فصل الواجهة عن الـpipeline القديم. "
            "لن تُشغّل هذه الصفحة أي backend قديم أو عملية مدفوعة "
            "حتى يتم ربط مرحلة V5 المقابلة واختبارها."
        )
        note.setObjectName("Subtle")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_logs_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("السجل والتشخيص")
        title.setObjectName("EpisodeTitle")
        layout.addWidget(title)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box, 1)
        return page

    def _change_page(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _log(self, message):
        self.log_box.append(message)

    def refresh_state(self):
        try:
            state = load_dashboard_state(self.repo_root)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "تعذر قراءة حالة سراج",
                str(exc),
            )
            return

        self.state = state
        self.top_stage_badge.setText(state.current_stage)
        self.top_lock_badge.setText(
            "الراوي: مقفول"
            if state.narrator_lock_status == "ACTIVE"
            else "الراوي: مشكلة"
        )

        self.card_stage.set_value(state.current_stage)
        self.card_progress.set_value(
            f"{state.completed_items} / {state.total_items}"
        )
        self.card_requests.set_value(str(state.planned_requests))
        self.card_chars.set_value(f"{state.total_characters:,}")
        self.card_pron.set_value(
            "PASS"
            if state.pronunciation_status == "PASS"
            else state.pronunciation_status
        )
        self.card_auth.set_value(
            "مصرّح" if state.authorized else "بانتظار التفويض"
        )

        self.safety_text.setText(
            "• Global Pronunciation Law V5.3: "
            f"{state.global_pronunciation_law}\n"
            "• الراوي الأساسي: مقفول ولا يسمح بالـfallback\n"
            "• Lock-before-network: فعّال\n"
            "• Automatic retry: ممنوع\n"
            "• أي فشل/timeout/نتيجة مجهولة: يحتاج تفويضًا جديدًا\n"
            "• لا يوجد سقف تكلفة وضعه المساعد"
        )

        self.tts_summary.setText(
            f"{state.provider} · {state.model_id} · "
            f"{state.planned_requests} طلبًا · "
            f"{state.total_characters:,} حرفًا"
        )

        pct = (
            int(state.completed_items / state.total_items * 100)
            if state.total_items
            else 0
        )
        self.tts_progress.setValue(pct)
        self.tts_status.setText(
            f"الحالة: {_status_text(state.final_tts_status)}"
        )

        self._fill_tts_table(state.queue_items)
        self.authorize_button.setEnabled(
            not state.authorized
            and state.completed_items < state.total_items
            and state.failed_items == 0
        )
        self.execute_button.setEnabled(
            state.authorized
            and state.completed_items < state.total_items
            and state.failed_items == 0
            and self.worker is None
        )

    def _fill_tts_table(self, items):
        self.tts_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [
                str(item.get("queue_index") or ""),
                str(item.get("segment_id") or ""),
                _status_text(str(item.get("status") or "")),
                f"{int(item.get('character_count_unicode', 0) or 0):,}",
                f"{float(item.get('pause_after_seconds', 0) or 0):.1f}s",
                (
                    f"{float(item.get('duration_seconds')):.2f}s"
                    if isinstance(
                        item.get("duration_seconds"),
                        (int, float),
                    )
                    else "—"
                ),
                str(item.get("output_path_relative") or ""),
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col in {0, 3, 4, 5}:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                self.tts_table.setItem(row, col, cell)

    def _authorize(self):
        dialog = AuthorizationDialog(self.state, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialog.confirmed:
            return

        try:
            authorize_final_tts(
                self.repo_root,
                dialog.input.text(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "فشل التفويض",
                str(exc),
            )
            self._log("AUTHORIZATION_FAILED: " + str(exc))
            return

        QMessageBox.information(
            self,
            "تم التفويض",
            "تم تسجيل التفويض وربطه ببصمة النص والإعدادات الحالية.",
        )
        self._log("FINAL_TTS_AUTHORIZATION=ACTIVE")
        self.refresh_state()

    def _execute_tts(self):
        if not getattr(self, "state", None) or not self.state.authorized:
            QMessageBox.warning(
                self,
                "التفويض مطلوب",
                "يجب تسجيل تفويض FINAL_TTS أولًا.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "بدء FINAL_TTS",
            "سيبدأ الآن إرسال طلبات ElevenLabs المصرّح بها فقط.\n"
            "لن تحدث أي إعادة محاولة تلقائية عند الفشل.\n\n"
            "هل تريد البدء؟",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.execute_button.setEnabled(False)
        self.authorize_button.setEnabled(False)

        self.worker = FinalTtsWorker(self.repo_root, self)
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.item_completed.connect(self._on_item_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished_successfully.connect(
            self._on_finished_successfully
        )
        self.worker.start()
        self._log("FINAL_TTS_EXECUTION_STARTED")

    def _on_progress(self, done, total, message):
        value = int(done / total * 100) if total else 0
        self.tts_progress.setValue(value)
        self.tts_status.setText(message)

    def _on_item_completed(self, queue_id, status):
        self._log(f"{queue_id}: {status}")
        self.refresh_state()

    def _on_failed(self, error):
        self._log("FINAL_TTS_STOPPED: " + error)
        QMessageBox.critical(
            self,
            "توقف FINAL_TTS",
            "توقف التنفيذ دون إعادة محاولة تلقائية.\n\n" + error,
        )
        self.worker = None
        self.refresh_state()

    def _on_finished_successfully(self):
        self._log("FINAL_TTS_EXECUTION_COMPLETE")
        QMessageBox.information(
            self,
            "اكتمل FINAL_TTS",
            "اكتملت جميع عناصر الصوت النهائي بنجاح.",
        )
        self.worker = None
        self.refresh_state()

    def _open_audio_folder(self):
        path = (
            self.repo_root
            / "projects"
            / "episode-002-adam-temptation-fall-repentance"
            / "audio"
            / "tts"
            / "final-v5-4"
        )
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def launch_production_studio(repo_root: Path) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("SIRAJ Production Studio")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    window = ProductionStudioWindow(repo_root)
    window.show()
    return app.exec()
