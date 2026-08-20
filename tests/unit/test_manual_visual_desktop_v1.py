from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton

from src.application.canonical_next_episode_manual_visual_pipeline_v1 import bootstrap_episode
from src.presentation.desktop.manual_visual_pipeline_dock_v1 import (
    install_manual_visual_pipeline_dock,
)


def test_desktop_manual_visual_surface_has_operator_actions_and_no_paid_generation(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    del app
    bootstrap_episode(tmp_path, "episode-051-desktop")
    window = QMainWindow()
    window.repo_root = tmp_path
    dock = install_manual_visual_pipeline_dock(window)
    dock.select_episode("episode-051-desktop")
    labels = {button.text() for button in dock.findChildren(QPushButton)}
    assert "حلقة جديدة" in labels
    assert "تصدير حزمة الإنتاج المرئي" in labels
    assert "استيراد المرئيات والتحقق منها" in labels
    assert "قفل المرئيات المقبولة" in labels
    assert "استكمال التجميع والمونتاج" in labels
    assert "تشغيل مراحل الجودة المنفصلة" in labels
    assert "المراجعة البشرية النهائية" in labels
    assert "بناء الماستر" in labels
    assert not any("Runware" in label or "توليد مدفوع" in label for label in labels)
