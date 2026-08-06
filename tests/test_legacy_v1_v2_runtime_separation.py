from pathlib import Path

from src.application.storyboard_runtime.cinematic_compiler import (
    CinematicSeriesCompiler,
)
from src.application.storyboard_runtime.cinematic_series import (
    GENERATED_VIDEO_HARD_LIMIT_SECONDS,
    HARD_MEDIA_BUDGET_USD,
    TARGET_MEDIA_BUDGET_USD,
)


def test_legacy_editorial_runtime_contract_is_restored() -> None:
    assert TARGET_MEDIA_BUDGET_USD == 40
    assert HARD_MEDIA_BUDGET_USD == 45
    assert GENERATED_VIDEO_HARD_LIMIT_SECONDS == 300


def test_v1_and_v2_production_controls_are_separate() -> None:
    v1 = Path(
        "src/application/episode_production_control_v1.py"
    ).read_text(encoding="utf-8")
    v2 = Path(
        "src/application/episode_production_control_v2.py"
    ).read_text(encoding="utf-8")
    assert "Compatibility facade" not in v1
    assert "HARD_CAP_USD = 40.0" in v1
    assert "Generic V2 paid-video budget control" in v2


def test_legacy_compiler_can_be_constructed() -> None:
    assert CinematicSeriesCompiler() is not None
