from __future__ import annotations

from pathlib import Path

from src.application.series_production_standard_v2_complete import (
    GENERATED_VIDEO_HARD_CAP_USD,
    GENERATED_VIDEO_TARGET_USD,
    TOTAL_EPISODE_HARD_CAP_USD,
    TTS_RESERVE_USD,
)


def test_complete_standard_v2_constitution() -> None:
    assert GENERATED_VIDEO_TARGET_USD == 30.0
    assert GENERATED_VIDEO_HARD_CAP_USD == 35.0
    assert TTS_RESERVE_USD == 3.0
    assert TOTAL_EPISODE_HARD_CAP_USD == 40.0


def test_standard_contract_markers() -> None:
    module = Path(
        "src/application/series_production_standard_v2_complete.py"
    ).read_text(encoding="utf-8")
    for marker in (
        "FAIL_CLOSED",
        "GLOBAL_PRESTIGE_CINEMATIC",
        "automatic_paid_retry",
        "maximum_still_panel_seconds",
        "BT709_LIMITED",
        "HUMAN_APPROVED_NO_NOTES",
        "READY_FOR_FULL_EPISODE_REBUILD_AUTHORIZATION",
    ):
        assert marker in module


def test_desktop_v2_panel_markers() -> None:
    panel = Path(
        "src/presentation/desktop/series_standard_v2_panel.py"
    ).read_text(encoding="utf-8")
    for marker in (
        "seriesProductionStandardV2Dock",
        "refreshSeriesProductionStandardV2Button",
        "openSeriesProductionStandardV2ReportButton",
        "install_series_standard_v2_dock",
    ):
        assert marker in panel
