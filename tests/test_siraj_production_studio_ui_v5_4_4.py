import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from src.presentation.desktop.production_studio_v5_4_4 import (
    ProductionStudioWindow,
)


def test_production_studio_window_offscreen_smoke():
    app = QApplication.instance() or QApplication([])
    repo = Path(__file__).resolve().parents[1]
    window = ProductionStudioWindow(repo)
    assert window.windowTitle().startswith("سراج")
    assert window.tts_table.rowCount() == 12
    window.close()
