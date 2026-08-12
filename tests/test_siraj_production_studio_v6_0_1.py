import os
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from src.presentation.desktop.production_studio_v6_0_1 import (
    ProductionStudioV601Window,
)


def test_window_smoke_and_resume_banner():
    app = QApplication.instance() or QApplication([])
    repo = Path(__file__).resolve().parents[1]
    window = ProductionStudioV601Window(repo)
    assert "V6.0.1" in window.windowTitle()
    assert window.stage_table.rowCount() >= 18
    assert "002" in window.resume_banner.text()
    window.close()
