from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setObjectName("muted")
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        caption_label = QLabel(caption)
        caption_label.setObjectName("metricCaption")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        if progress is not None:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(max(0, min(100, progress)))
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            layout.addWidget(bar)
        layout.addWidget(caption_label)


class StatusPill(QFrame):
    def __init__(self, text: str, tone: str = "muted", parent: QWidget | None = None):
        super().__init__(parent)
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
            "padding: 3px 8px;"
            "}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(text))


class PreviewCanvas(QWidget):
    """A dependency-free cinematic placeholder until a real frame is available."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.overlay_text = "لا توجد معاينة فيديو بعد"
        self.shot_text = "—"

    def set_context(self, overlay_text: str, shot_text: str) -> None:
        self.overlay_text = overlay_text
        self.shot_text = shot_text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
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

        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            rect.adjusted(20, 20, -20, -45),
            Qt.AlignmentFlag.AlignCenter,
            self.overlay_text,
        )

        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#e5e9ec"))
        painter.drawText(
            rect.adjusted(16, 16, -16, -14),
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
            self.shot_text,
        )


class WorkflowStrip(Panel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        title = QLabel("سير العمل الإنتاجي للحلقة")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)
        stages = (
            ("النص", True),
            ("الستوريبورد", True),
            ("المراجعة الشرعية والبصرية", True),
            ("حزم اللقطات", False),
            ("توليد الفيديو", False),
            ("المونتاج", False),
            ("جاهز للنشر", False),
        )
        for index, (label, complete) in enumerate(stages):
            stage = QLabel(("✓  " if complete else "○  ") + label)
            stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage.setMinimumHeight(42)
            color = COLORS["green"] if complete else COLORS["muted"]
            if index == 3:
                color = COLORS["gold"]
            stage.setStyleSheet(
                f"color: {color}; background: #0a141d; border: 1px solid #2b3a47;"
                "border-radius: 9px; padding: 6px; font-weight: 600;"
            )
            row.addWidget(stage, 1)
        layout.addLayout(row)
