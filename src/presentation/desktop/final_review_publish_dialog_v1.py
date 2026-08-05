from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.application.final_review_publish_package_v1 import (
    REQUIRED_CHECKLIST_KEYS,
    FinalReviewError,
    approve_final_review_and_build_publish_package,
    load_final_review_status,
    request_final_review_changes,
    suggest_publish_metadata,
)


CHECKLIST_LABELS = {
    "watched_full_episode": "شاهدت الحلقة كاملة من البداية إلى النهاية",
    "reviewed_audio_and_sync": "راجعت الصوت والتزامن وعدم وجود انقطاع",
    "reviewed_visual_continuity": "راجعت الاستمرارية البصرية والانتقالات",
    "reviewed_historical_semantic_accuracy": "راجعت الدقة التاريخية والدلالية بشريًا",
    "confirmed_no_forbidden_music": "تأكدت من عدم وجود موسيقى محظورة",
    "confirmed_no_private_or_sensitive_data": "تأكدت من عدم وجود بيانات خاصة أو حساسة",
    "approved_title_description_and_tags": "اعتمدت العنوان والوصف والوسوم",
}

CATEGORY_LABELS = {
    "VISUAL": "مشكلة بصرية",
    "AUDIO": "مشكلة صوتية",
    "CONTENT_ACCURACY": "مشكلة في الدقة أو المحتوى",
    "METADATA": "العنوان أو الوصف أو الوسوم فقط",
    "OTHER": "مشكلة أخرى",
}


class FinalReviewPublishDialog(QDialog):
    def __init__(
        self,
        repo_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = repo_root.resolve()
        self.checkboxes: dict[str, QCheckBox] = {}
        self.setObjectName("finalReviewPublishDialog")
        self.setWindowTitle("سراج — المراجعة النهائية وحزمة النشر")
        self.resize(920, 760)
        self._build_ui()
        self._load_defaults()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("المراجعة البشرية النهائية")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("finalReviewStatusLabel")
        layout.addWidget(self.status_label)

        form = QFormLayout()
        self.reviewer_input = QLineEdit("CREATOR")
        self.reviewer_input.setObjectName("finalReviewerInput")
        form.addRow("المراجع:", self.reviewer_input)

        self.title_input = QLineEdit()
        self.title_input.setObjectName("publishTitleInput")
        form.addRow("عنوان النشر:", self.title_input)

        self.description_input = QPlainTextEdit()
        self.description_input.setObjectName("publishDescriptionInput")
        self.description_input.setMaximumHeight(120)
        form.addRow("الوصف:", self.description_input)

        self.tags_input = QLineEdit()
        self.tags_input.setObjectName("publishTagsInput")
        form.addRow("الوسوم:", self.tags_input)

        self.visibility_combo = QComboBox()
        self.visibility_combo.setObjectName("publishVisibilityPreference")
        self.visibility_combo.addItems(["PRIVATE", "UNLISTED", "PUBLIC"])
        form.addRow("تفضيل الظهور الأولي:", self.visibility_combo)
        layout.addLayout(form)

        checklist_title = QLabel("قائمة الاعتماد الإلزامية")
        checklist_title.setObjectName("sectionTitle")
        layout.addWidget(checklist_title)
        for key in REQUIRED_CHECKLIST_KEYS:
            checkbox = QCheckBox(CHECKLIST_LABELS[key])
            checkbox.setObjectName("finalReviewChecklist_" + key)
            self.checkboxes[key] = checkbox
            layout.addWidget(checkbox)

        notes_title = QLabel("ملاحظات المراجعة")
        notes_title.setObjectName("sectionTitle")
        layout.addWidget(notes_title)
        self.notes_input = QPlainTextEdit()
        self.notes_input.setObjectName("finalReviewNotesInput")
        self.notes_input.setMaximumHeight(90)
        layout.addWidget(self.notes_input)

        change_row = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.setObjectName("finalReviewChangeCategory")
        for value, label in CATEGORY_LABELS.items():
            self.category_combo.addItem(label, value)
        change_row.addWidget(self.category_combo, 2)
        self.shot_ids_input = QLineEdit()
        self.shot_ids_input.setObjectName("finalReviewShotIdsInput")
        self.shot_ids_input.setPlaceholderText("معرّفات اللقطات — اختيارية، مفصولة بفواصل")
        change_row.addWidget(self.shot_ids_input, 3)
        layout.addLayout(change_row)

        actions = QHBoxLayout()
        self.approve_button = QPushButton("اعتماد وبناء حزمة النشر")
        self.approve_button.setObjectName("approveFinalReviewButton")
        self.approve_button.setMinimumHeight(44)
        self.approve_button.clicked.connect(self._approve)
        actions.addWidget(self.approve_button)

        self.request_changes_button = QPushButton("طلب إصلاح محدد")
        self.request_changes_button.setObjectName("requestFinalReviewChangesButton")
        self.request_changes_button.setMinimumHeight(44)
        self.request_changes_button.clicked.connect(self._request_changes)
        actions.addWidget(self.request_changes_button)
        layout.addLayout(actions)

        open_row = QHBoxLayout()
        self.open_video_button = QPushButton("عرض الحلقة")
        self.open_video_button.clicked.connect(self._open_video)
        open_row.addWidget(self.open_video_button)
        self.open_qa_button = QPushButton("فتح تقرير QA")
        self.open_qa_button.clicked.connect(self._open_qa)
        open_row.addWidget(self.open_qa_button)
        self.open_package_button = QPushButton("فتح حزمة النشر")
        self.open_package_button.clicked.connect(self._open_package)
        open_row.addWidget(self.open_package_button)
        self.close_button = QPushButton("إغلاق")
        self.close_button.clicked.connect(self.accept)
        open_row.addWidget(self.close_button)
        layout.addLayout(open_row)

        note = QLabel(
            "لا يرفع سراج الفيديو إلى YouTube تلقائيًا ولا يخزن بيانات دخول. "
            "الاعتماد ينشئ فيديوًا مرجعيًا بالـSHA-256 وملفات العنوان والوصف "
            "والوسوم وقائمة رفع يدوية فقط."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _load_defaults(self) -> None:
        try:
            metadata = suggest_publish_metadata(self.repo_root)
        except FinalReviewError:
            return
        self.title_input.setText(str(metadata.get("title", "")))
        self.description_input.setPlainText(str(metadata.get("description", "")))
        tags = metadata.get("tags", [])
        if isinstance(tags, list):
            self.tags_input.setText(", ".join(str(value) for value in tags))
        visibility = str(metadata.get("visibility_preference", "PRIVATE"))
        index = self.visibility_combo.findText(visibility)
        if index >= 0:
            self.visibility_combo.setCurrentIndex(index)

    def _status(self) -> dict:
        return load_final_review_status(self.repo_root)

    def _refresh(self) -> None:
        status = self._status()
        state = str(status.get("status", "UNKNOWN"))
        messages = {
            "AWAITING_HUMAN_FINAL_REVIEW": (
                "اجتازت الحلقة QA. شاهدها وراجعها ثم اعتمدها أو اطلب إصلاحًا محددًا."
            ),
            "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED": (
                "هناك طلب إصلاح مفتوح. يمكن اعتماد تعديلات metadata فقط مباشرة؛ "
                "أما تغييرات الفيديو أو الصوت أو المحتوى فتحتاج إعادة QA."
            ),
            "READY_TO_PUBLISH": (
                "تم الاعتماد وبناء الحزمة. الرفع إلى YouTube يدوي فقط."
            ),
        }
        self.status_label.setText(messages.get(state, state))
        ready = bool(status.get("ready"))
        can_approve = bool(status.get("can_approve"))
        self.approve_button.setEnabled(can_approve)
        self.request_changes_button.setEnabled(ready)
        final_path = Path(str(status.get("final_master_path", "")))
        qa_path = Path(str(status.get("qa_report_path", "")))
        package_dir = Path(str(status.get("publish_package_dir", "")))
        self.open_video_button.setEnabled(final_path.is_file())
        self.open_qa_button.setEnabled(qa_path.is_file())
        self.open_package_button.setEnabled(package_dir.is_dir())

    def _checklist(self) -> dict[str, bool]:
        return {
            key: checkbox.isChecked()
            for key, checkbox in self.checkboxes.items()
        }

    def _approve(self) -> None:
        try:
            result = approve_final_review_and_build_publish_package(
                self.repo_root,
                reviewer=self.reviewer_input.text(),
                checklist=self._checklist(),
                title=self.title_input.text(),
                description=self.description_input.toPlainText(),
                tags=self.tags_input.text(),
                notes=self.notes_input.toPlainText(),
                visibility_preference=self.visibility_combo.currentText(),
            )
        except FinalReviewError as exc:
            QMessageBox.critical(self, "تعذر الاعتماد", str(exc))
            return
        QMessageBox.information(
            self,
            "الحلقة جاهزة للنشر",
            "تم تثبيت المراجعة البشرية وبناء حزمة النشر المحلية."
            + "\nالفيديو: "
            + str(result.final_master_path)
            + "\nلا يوجد رفع تلقائي أو طلب API.",
        )
        self._refresh()

    def _request_changes(self) -> None:
        category = str(self.category_combo.currentData())
        shot_ids = [
            value.strip()
            for value in self.shot_ids_input.text().replace("،", ",").split(",")
            if value.strip()
        ]
        try:
            result = request_final_review_changes(
                self.repo_root,
                reviewer=self.reviewer_input.text(),
                categories=[category],
                notes=self.notes_input.toPlainText(),
                shot_ids=shot_ids,
            )
        except FinalReviewError as exc:
            QMessageBox.critical(self, "تعذر تسجيل طلب الإصلاح", str(exc))
            return
        QMessageBox.information(
            self,
            "تم تسجيل طلب الإصلاح",
            "سُجل الطلب دون أي إعادة مدفوعة تلقائية."
            + "\nالمسار: "
            + str(result.repair_request_path),
        )
        self._refresh()

    def _open_video(self) -> None:
        path = Path(str(self._status().get("final_master_path", "")))
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_qa(self) -> None:
        path = Path(str(self._status().get("qa_report_path", "")))
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_package(self) -> None:
        path = Path(str(self._status().get("publish_package_dir", "")))
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
