from __future__ import annotations

from pathlib import Path

import pytest

from src.presentation.desktop.shorts_derivative_dock_v1 import desktop_dock_descriptor


REPO = Path(__file__).resolve().parents[2]


def test_shorts_dock_is_existing_window_surface_and_geometry_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src.presentation.desktop.main_window import SirajDesktopWindow

    app = QApplication.instance() or QApplication([])
    window = SirajDesktopWindow(REPO)
    try:
        window.show()
        app.processEvents()
        dock = window._shorts_derivative_dock
        descriptor = desktop_dock_descriptor()
        assert descriptor["second_gui_created"] is False
        assert descriptor["hard_boundaries"]["provider_calls"] is False
        assert descriptor["hard_boundaries"]["network_calls"] is False
        assert descriptor["hard_boundaries"]["paid_calls"] is False
        assert descriptor["hard_boundaries"]["automatic_publication"] is False
        for width, height in ((1280, 720), (1520, 900), (1920, 1080), (2560, 1440)):
            window.resize(width, height)
            window._navigate("shorts")
            app.processEvents()
            assert dock.width() > 0
            assert dock.height() > 0
            assert dock.widget().minimumHeight() > 0
            assert dock.isVisible()
        assert window.nav_buttons["shorts"].property("active") is True
    finally:
        window.close()
        app.processEvents()
