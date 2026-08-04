from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .models import EpisodeRecord, EpisodeStage
from .theme import COLORS


class Panel(QFrame):
    def __init__(self, *, object_name: str = "panel", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)


class MetricCard(Panel):
    def __init__(
        self,
        title: str,
        value: str,
        caption: str,
        *,
        progress: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setObjectName("muted")
        title_label.setWordWrap(True)
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        caption_label = QLabel(caption)
        caption_label.setObjectName("metricCaption")
        caption_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        if progress is not None:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(max(0, min(100, progress)))
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            layout.addWidget(bar)
        layout.addWidget(caption_label)


class StatusPill(QFrame):
    def __init__(self, text: str, tone: str = "muted", parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        colors = {
            "green": ("#103325", COLORS["green"]),
            "gold": ("#332714", COLORS["gold"]),
            "blue": ("#102b3b", COLORS["blue"]),
            "orange": ("#382313", COLORS["orange"]),
            "red": ("#381919", COLORS["red"]),
            "muted": (COLORS["surface_alt"], COLORS["muted"]),
        }
        background, foreground = colors.get(tone, colors["muted"])
        self.setStyleSheet(
            "QFrame {"
            f"background-color: {background};"
            f"border: 1px solid {foreground};"
            "border-radius: 9px;"
            "}"
            "QLabel {"
            f"color: {foreground};"
            "font-weight: 600;"
            "padding: 3px 7px;"
            "}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label)

    def set_text(self, text: str) -> None:
        self.label.setText(text)
        self.label.setToolTip(text)


class PreviewCanvas(QWidget):
    """Visible cinematic 16:9 preview placeholder for every dashboard size."""

    MIN_PREVIEW_HEIGHT = 169
    MAX_PREVIEW_HEIGHT = 232

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, self.MIN_PREVIEW_HEIGHT)
        self.setMaximumHeight(self.MAX_PREVIEW_HEIGHT)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.overlay_text = "لا توجد معاينة فيديو بعد"
        self.shot_text = "—"
        self.beat_text = "—"
        self.state_text = "غير مولد"

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return max(
            self.MIN_PREVIEW_HEIGHT,
            min(self.MAX_PREVIEW_HEIGHT, round(max(1, width) * 9 / 16)),
        )

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(360, 203)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        target = self.heightForWidth(self.width())
        if abs(self.height() - target) > 1:
            self.setFixedHeight(target)

    def set_context(
        self,
        overlay_text: str,
        shot_text: str,
        state_text: str = "غير مولد",
        beat_text: str = "—",
    ) -> None:
        self.overlay_text = overlay_text
        self.shot_text = shot_text
        self.state_text = state_text
        self.beat_text = beat_text
        self.setToolTip(
            f"الحالة: {state_text}\nاللقطة: {shot_text}\nالوحدة: {beat_text}"
        )
        self.updateGeometry()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        sky = QLinearGradient(0, 0, rect.width(), rect.height())
        sky.setColorAt(0.0, QColor("#182b3b"))
        sky.setColorAt(0.45, QColor("#b47b32"))
        sky.setColorAt(1.0, QColor("#171a1c"))
        painter.fillRect(rect, sky)

        def mountain(points: list[tuple[float, float]], color: str) -> None:
            path = QPainterPath()
            path.moveTo(QPointF(0, rect.height()))
            for x_factor, y_factor in points:
                path.lineTo(QPointF(rect.width() * x_factor, rect.height() * y_factor))
            path.lineTo(QPointF(rect.width(), rect.height()))
            path.closeSubpath()
            painter.fillPath(path, QColor(color))

        mountain(
            [(0.0, 0.66), (0.16, 0.30), (0.32, 0.64), (0.48, 0.38), (0.7, 0.65), (1.0, 0.4)],
            "#273440",
        )
        mountain(
            [(0.0, 0.78), (0.24, 0.54), (0.43, 0.76), (0.67, 0.52), (1.0, 0.72)],
            "#18232c",
        )

        painter.setPen(QPen(QColor("#e8ad35"), 2))
        painter.drawLine(0, rect.height() - 5, rect.width(), rect.height() - 5)

        state_rect = QRectF(12, 12, min(135, rect.width() * 0.43), 28)
        painter.setPen(QPen(QColor("#e8ad35"), 1))
        painter.setBrush(QColor(7, 16, 25, 210))
        painter.drawRoundedRect(state_rect, 8, 8)
        painter.setPen(QColor("#e8ad35"))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(state_rect, Qt.AlignmentFlag.AlignCenter, self.state_text)

        painter.setPen(QColor("#ffffff"))
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(
            rect.adjusted(18, 40, -18, -54),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.overlay_text,
        )

        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#e5e9ec"))
        footer = f"{self.shot_text}  •  {self.beat_text}"
        painter.drawText(
            rect.adjusted(14, 14, -14, -12),
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
            footer,
        )


class WorkflowStrip(Panel):
    _LABELS = (
        "النص",
        "الستوريبورد",
        "المراجعة الشرعية والبصرية",
        "حزم اللقطات",
        "توليد الفيديو",
        "المونتاج",
        "جاهز للنشر",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 9, 13, 11)
        title = QLabel("سير العمل الإنتاجي للحلقة")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.stage_labels: list[QLabel] = []
        row = QGridLayout()
        row.setHorizontalSpacing(6)
        row.setVerticalSpacing(6)
        for index, label in enumerate(self._LABELS):
            stage = QLabel(label)
            stage.setWordWrap(True)
            stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage.setMinimumHeight(46)
            stage.setMinimumWidth(0)
            self.stage_labels.append(stage)
            row.addWidget(stage, 0, index)
            row.setColumnStretch(index, 1)
        layout.addLayout(row)
        self.set_episode(None)

    def _style_stage(self, label: QLabel, state: str) -> None:
        styles = {
            "complete": ("✓", COLORS["green"], "#0d2a1f"),
            "active": ("●", COLORS["gold"], "#2a2415"),
            "waiting": ("○", COLORS["blue"], "#0d2230"),
            "blocked": ("○", COLORS["muted"], "#0a141d"),
            "failed": ("!", COLORS["red"], "#2a1212"),
        }
        marker, color, background = styles[state]
        base_text = label.property("stageText") or label.text().lstrip("✓●○! ")
        label.setProperty("stageText", base_text)
        label.setText(f"{marker}  {base_text}")
        label.setStyleSheet(
            f"color: {color}; background: {background}; border: 1px solid {color};"
            "border-radius: 9px; padding: 5px; font-weight: 600;"
        )

    def set_episode(self, episode: EpisodeRecord | None) -> None:
        if episode is None:
            states = ["blocked"] * len(self.stage_labels)
        else:
            has_manifest = episode.manifest_path is not None
            has_package = episode.current_shot_id != "—"
            has_generated = episode.generated_shot_count > 0
            has_final = episode.final_video_path is not None
            states = [
                "complete" if has_manifest else "active",
                "complete" if has_manifest else "waiting",
                "complete" if has_manifest else "waiting",
                "complete" if has_package and has_generated else ("active" if has_package else "waiting"),
                "complete" if has_final else ("active" if has_generated else "waiting"),
                "complete" if has_final else "blocked",
                "complete" if episode.stage == EpisodeStage.PUBLISH_READY else (
                    "active" if episode.stage == EpisodeStage.VIDEO_REVIEW else "blocked"
                ),
            ]
        for label, state in zip(self.stage_labels, states, strict=True):
            self._style_stage(label, state)
