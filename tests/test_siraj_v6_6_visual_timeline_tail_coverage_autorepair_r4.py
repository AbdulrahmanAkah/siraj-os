from pathlib import Path

from src.application.siraj_visual_timeline_coverage_autorepair_v6_6_r4 import (
    is_visual_timeline_coverage_failure,
)


def test_exact_coverage_error_is_detected():
    exc = RuntimeError(
        "VISUAL_TIMELINE_DOES_NOT_COVER_EPISODE:"
        "timeline=592.021:episode=623.584"
    )
    assert is_visual_timeline_coverage_failure(exc)


def test_wrapper_contains_r4_local_editorial_repair():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/application/siraj_autopilot_v6_6.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_VISUAL_TIMELINE_COVERAGE_AUTOREPAIR_V6_6_R4" in source
    assert "repair_visual_timeline_coverage" in source
    assert '"MEDIA_COST_PREFLIGHT"' in source
    assert "is_visual_timeline_coverage_failure" in source


def test_r4_uses_existing_luna_stage_not_new_retry_stage():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_visual_timeline_coverage_autorepair_v6_6_r4.py"
    ).read_text(encoding="utf-8-sig")

    assert 'PROMPT_STAGE = "LUNA_SEMANTIC_PROMPT_DIRECTION"' in source
    assert "master_authorization_active" in source
    assert '"paid_retry": False' in source
    assert '"append_tail_items_only": True' in source
