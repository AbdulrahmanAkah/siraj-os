from __future__ import annotations

from pathlib import Path
import inspect

import pytest

from src.presentation.desktop.shorts_derivative_dock_v1 import (
    ALL_FILE_FILTER,
    SUBTITLE_FILE_FILTER,
    VIDEO_FILE_FILTER,
    desktop_dock_descriptor,
    configure_episode_file_dialog,
)


REPO = Path(__file__).resolve().parents[2]


def test_user_facing_descriptor_has_five_progressive_steps_and_boundaries() -> None:
    descriptor = desktop_dock_descriptor()

    assert descriptor["visible_stages"] == ["EPISODE", "SHORTS", "PRODUCE", "REVIEW", "SAVE"]
    assert descriptor["hard_boundaries"]["provider_calls"] is False
    assert descriptor["hard_boundaries"]["network_calls"] is False
    assert descriptor["hard_boundaries"]["paid_calls"] is False
    assert descriptor["hard_boundaries"]["automatic_publication"] is False


def test_episode_and_transcript_filter_contracts_are_explicit() -> None:
    assert VIDEO_FILE_FILTER == "Video files (*.mp4 *.mov *.mkv *.m4v *.webm *.avi)"
    assert ALL_FILE_FILTER == "All files (*.*)"
    assert SUBTITLE_FILE_FILTER == "Subtitle files (*.srt *.vtt *.json)"
    picker_source = inspect.getsource(configure_episode_file_dialog)
    assert "DontUseNativeDialog, False" in picker_source
    assert "ExistingFile" in picker_source
    assert "setNameFilters([VIDEO_FILE_FILTER, ALL_FILE_FILTER])" in picker_source


def test_shorts_window_exposes_only_user_actions_when_qt_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src.presentation.desktop.main_window import SirajDesktopWindow

    app = QApplication.instance() or QApplication([])
    window = SirajDesktopWindow(REPO)
    try:
        window.show()
        window._navigate("shorts")
        app.processEvents()
        dock = window._shorts_derivative_dock
        assert dock.select_button.text() == "اختيار الحلقة"
        assert dock.open_library_button.text() == "فتح مكتبة الشورتس"
        visible_text = " ".join(widget.text() for widget in dock.findChildren(type(dock.select_button)) if widget.isVisible())
        assert "Generate Render Plans" not in visible_text
        assert "Automated QA" not in visible_text
        assert "BLOCKED" not in visible_text
    finally:
        window.close()
        app.processEvents()


def test_zero_candidates_keep_recovery_message_visible_without_empty_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from types import SimpleNamespace

    from PySide6.QtWidgets import QApplication

    from src.presentation.desktop.shorts_derivative_dock_v1 import ShortsDerivativeDock

    app = QApplication.instance() or QApplication([])
    dock = ShortsDerivativeDock(REPO)
    try:
        dock.show()
        dock._analysis_ready(SimpleNamespace(candidates=(SimpleNamespace(status="BLOCKED"),)))
        app.processEvents()
        assert dock.zero_candidates_card.isVisible()
        assert not dock.candidate_preview.isVisible()
        assert not dock.candidates.isVisible()
        assert dock.zero_candidates_card.height() <= 160
        assert dock.zero_candidates_card.y() <= 180
        assert dock.show_excluded_button.isVisible()
    finally:
        dock.close()
        app.processEvents()
