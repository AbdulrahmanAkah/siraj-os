"""PySide6 status dock for SIRAJ SERIES PRODUCTION STANDARD V2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (
        QDockWidget,
        QFrame,
        QGridLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - desktop optional dependency
    Qt = QTimer = QUrl = QDesktopServices = None  # type: ignore
    QDockWidget = QFrame = QGridLayout = QLabel = object  # type: ignore
    QPushButton = QVBoxLayout = QWidget = object  # type: ignore


SNAPSHOT_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "desktop-series-production-standard-v2-snapshot.json"
)


def _find_repo_root() -> Path:
    starts = (
        Path.cwd(),
        Path(__file__).resolve(),
    )
    for start in starts:
        current = start if start.is_dir() else start.parent
        for candidate in (current, *current.parents):
            if (candidate / ".git").exists() and (
                candidate / "projects"
            ).is_dir():
                return candidate
    return Path.cwd()


def _read_snapshot(repo: Path) -> dict[str, Any]:
    path = repo / SNAPSHOT_REL
    if not path.is_file():
        return {
            "standard_status": "STANDARD_V2_SNAPSHOT_MISSING",
            "standard_complete": False,
            "next_action_ar": "تشغيل حزمة إغلاق معيار الإنتاج V2",
            "quality_gate": {"blocking_issue_count": 1},
            "narration": {"status": "UNKNOWN", "blocks": 0},
            "budget": {},
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {
            "standard_status": "STANDARD_V2_SNAPSHOT_INVALID",
            "standard_complete": False,
            "next_action_ar": "إصلاح لقطة حالة المعيار",
            "quality_gate": {"blocking_issue_count": 1},
            "narration": {"status": "UNKNOWN", "blocks": 0},
            "budget": {},
        }
    return value if isinstance(value, dict) else {}


class SeriesStandardV2Panel(QWidget):  # type: ignore[misc]
    def __init__(self, repo_root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repo_root = repo_root
        self.setObjectName("seriesProductionStandardV2Panel")
        self._labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        title = QLabel("SIRAJ SERIES PRODUCTION STANDARD V2")
        title.setObjectName("seriesProductionStandardV2Title")
        title.setStyleSheet(
            "font-size: 17px; font-weight: 700; color: #d5b36a;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "بوابة الجاهزية السينمائية والتقنية والمالية قبل إنتاج الحلقة"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #c8c8c8;")
        layout.addWidget(subtitle)

        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #171717; border: 1px solid #39332a; "
            "border-radius: 8px; padding: 8px; }"
        )
        grid = QGridLayout(card)
        rows = (
            ("status", "حالة المعيار"),
            ("narration", "الصوت"),
            ("budget", "الميزانية"),
            ("quality", "بوابات الجودة"),
            ("next", "الخطوة التالية"),
        )
        for row, (key, label) in enumerate(rows):
            name = QLabel(label)
            name.setStyleSheet("color: #9b9b9b;")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setStyleSheet("color: #f1f1f1; font-weight: 600;")
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self._labels[key] = value
        layout.addWidget(card)

        refresh = QPushButton("تحديث حالة المعيار")
        refresh.setObjectName("refreshSeriesProductionStandardV2Button")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)

        open_report = QPushButton("فتح تقرير الجاهزية")
        open_report.setObjectName("openSeriesProductionStandardV2ReportButton")
        open_report.clicked.connect(self.open_report)
        layout.addWidget(open_report)

        note = QLabel(
            "لن تُوسم الحلقة «جاهزة للنشر» ما لم تمر جميع البوابات "
            "المانعة. لا توجد إعادة مدفوعة خفية."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #a8a8a8; font-size: 11px;")
        layout.addWidget(note)
        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        snapshot = _read_snapshot(self.repo_root)
        complete = bool(snapshot.get("standard_complete"))
        status = str(snapshot.get("standard_status") or "UNKNOWN")
        narration = snapshot.get("narration")
        budget = snapshot.get("budget")
        quality = snapshot.get("quality_gate")
        narration = narration if isinstance(narration, dict) else {}
        budget = budget if isinstance(budget, dict) else {}
        quality = quality if isinstance(quality, dict) else {}

        self._labels["status"].setText(
            ("مكتمل — " if complete else "محجوب — ") + status
        )
        self._labels["status"].setStyleSheet(
            "color: #79c995; font-weight: 700;"
            if complete
            else "color: #e08a78; font-weight: 700;"
        )
        self._labels["narration"].setText(
            f"{narration.get('status', 'UNKNOWN')} — "
            f"{narration.get('blocks', 0)} كتلة"
        )
        self._labels["budget"].setText(
            f"فيديو {budget.get('generated_video_target_usd', 30)}$ / "
            f"{budget.get('generated_video_hard_cap_usd', 35)}$، "
            f"إجمالي أقصى {budget.get('total_episode_hard_cap_usd', 40)}$"
        )
        self._labels["quality"].setText(
            f"عيوب مانعة: {quality.get('blocking_issue_count', 0)} — "
            f"{quality.get('release_policy', 'FAIL_CLOSED')}"
        )
        self._labels["next"].setText(
            str(snapshot.get("next_action_ar") or "—")
        )

    def open_report(self) -> None:
        report = (
            self.repo_root
            / "projects/episode-001-adam/orchestration/"
            "series-production-standard-v2-readiness.json"
        )
        if report.is_file():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(report.resolve()))
            )


def _install(window: Any) -> None:
    if Qt is None or getattr(
        window, "_series_standard_v2_dock_installed", False
    ):
        return
    repo = _find_repo_root()
    dock = QDockWidget("معيار الإنتاج V2", window)
    dock.setObjectName("seriesProductionStandardV2Dock")
    dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea
        | Qt.DockWidgetArea.RightDockWidgetArea
    )
    dock.setWidget(SeriesStandardV2Panel(repo, dock))
    window.addDockWidget(
        Qt.DockWidgetArea.RightDockWidgetArea,
        dock,
    )
    window._series_standard_v2_dock_installed = True
    window._series_standard_v2_dock = dock


def install_series_standard_v2_dock(window: Any) -> None:
    """Install after the existing main window finishes constructing."""
    if QTimer is None:
        return
    QTimer.singleShot(0, lambda: _install(window))
