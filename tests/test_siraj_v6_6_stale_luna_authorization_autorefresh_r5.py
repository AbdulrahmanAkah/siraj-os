from pathlib import Path


def test_v66_refreshes_pre_network_stale_luna_authorization():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/application/siraj_autopilot_v6_6.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_STALE_LUNA_AUTH_AUTOREFRESH_V6_6_R5" in source
    assert "def _is_pre_network_luna_authorization_invalid(" in source
    assert "def _archive_stale_luna_authorization(" in source
    assert "def _execute_paid_stage_with_master_auth_refresh(" in source
    assert "luna_authorization_path" in source
    assert "_ensure_legacy_stage_authorized(" in source
    assert "return v64.execute_current_stage(repo)" in source


def test_paid_retry_law_is_not_weakened():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/siraj_episode_master_authorization_v6_6.py"
    ).read_text(encoding="utf-8-sig")

    assert "PAID_RETRY_CONFIRMATION_PHRASE" in source
    assert "automatic_paid_retry" in source
    assert "automatic_paid_resubmission" in source


def test_r4_tail_repair_is_preserved():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/application/siraj_autopilot_v6_6.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_VISUAL_TIMELINE_COVERAGE_AUTOREPAIR_V6_6_R4" in source
    assert "repair_visual_timeline_coverage" in source
