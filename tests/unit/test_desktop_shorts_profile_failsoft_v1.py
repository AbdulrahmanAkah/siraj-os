from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow

import src.presentation.desktop.main_window as main_window
from src.application.shorts_derivative_engine_v1 import ShortsProfileError


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_shorts_profile_mismatch_is_failsoft(monkeypatch):
    _app()
    window = QMainWindow()

    def fail(_window):
        raise ShortsProfileError(
            "SHORT_PROFILE_INVALID",
            "PROFILE_VERSION_MISMATCH",
        )

    monkeypatch.setattr(
        main_window,
        "install_shorts_derivative_dock",
        fail,
    )

    main_window._install_optional_shorts_derivative_dock(window)

    assert "PROFILE_VERSION_MISMATCH" in window._shorts_dock_startup_error
    assert "Shorts workspace unavailable" in window.statusBar().currentMessage()


def test_non_profile_shorts_startup_error_is_not_swallowed(monkeypatch):
    _app()
    window = QMainWindow()

    def fail(_window):
        raise RuntimeError("UNRELATED_SHORTS_STARTUP_BUG")

    monkeypatch.setattr(
        main_window,
        "install_shorts_derivative_dock",
        fail,
    )

    with pytest.raises(RuntimeError, match="UNRELATED_SHORTS_STARTUP_BUG"):
        main_window._install_optional_shorts_derivative_dock(window)
