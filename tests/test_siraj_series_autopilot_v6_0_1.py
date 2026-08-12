from pathlib import Path

from src.application.siraj_series_autopilot_v6_0_1 import (
    EP2_ID,
    classify_failure,
    resolve_resume_state,
)


def test_episode_002_resumes_at_final_tts_or_later():
    repo = Path(__file__).resolve().parents[1]
    state = resolve_resume_state(repo)
    assert state.episode_id == EP2_ID
    assert state.mode == "RESUME_EXISTING_EPISODE"
    assert state.resume_stage in {
        "FINAL_TTS",
        "AUDIO_TIMESTAMPS_AND_BEATS",
    }
    assert "PRONUNCIATION_AND_PERFORMANCE_GATE" in state.completed_stages
    assert "TOPIC_SELECTION" in state.protected_completed_stages


def test_paid_retry_never_automatic():
    d = classify_failure("NETWORK_RESULT_UNKNOWN_NO_AUTOMATIC_RESUBMISSION")
    assert d.automatic_paid_retry_allowed is False
    assert d.human_action_required is True


def test_safe_local_can_auto_repair():
    d = classify_failure("JSONDecodeError")
    assert d.automatic_repair_allowed is True
    assert d.automatic_paid_retry_allowed is False


def test_structural_change_stops():
    d = classify_failure("SCHEMA_MIGRATION_REQUIRED")
    assert d.human_action_required is True
    assert d.automatic_repair_allowed is False
