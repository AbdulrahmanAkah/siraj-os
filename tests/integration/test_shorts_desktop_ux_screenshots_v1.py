from __future__ import annotations

from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCREENSHOT_STATES = (
    "01_landing",
    "02_episode_selected",
    "03_transcript_missing",
    "04_analysis_running",
    "05_candidates",
    "06_candidate_details",
    "07_portfolio",
    "08_production_ready",
    "09_rendering",
    "10_qa_pass",
    "11_review_playback",
    "12_detailed_review",
    "13_export_ready",
    "14_saved",
    "15_error",
    "16_zero_candidates",
    "17_existing_shorts",
)


def test_short_ux_screenshots_are_captured_locally(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src.presentation.desktop.main_window import SirajDesktopWindow

    app = QApplication.instance() or QApplication([])
    window = SirajDesktopWindow(REPO)
    try:
        window.show()
        window._navigate("shorts")
        dock = window._shorts_derivative_dock
        output = tmp_path / "shorts-ux-screenshots"
        output.mkdir()
        for state in SCREENSHOT_STATES:
            page_state = "landing" if state.endswith("landing") else "source" if "episode_selected" in state or "transcript_missing" in state or "existing_shorts" in state else "analysis" if "analysis" in state else "candidates" if "candidate" in state or "zero" in state else "portfolio" if "portfolio" in state else "production" if "production" in state or "rendering" in state or "qa_pass" in state else "review" if "review" in state else "save"
            dock._set_state(page_state)
            dock._set_message(state.replace("_", " "))
            app.processEvents()
            assert dock.grab().save(str(output / f"{state}.png"))
        assert len(list(output.glob("*.png"))) == len(SCREENSHOT_STATES)
    finally:
        window.close()
        app.processEvents()
