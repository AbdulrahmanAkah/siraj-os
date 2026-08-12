import json
import pytest
from src.application.siraj_v4_plus_contract_v1 import (
    EpisodeContext,
    SirajV4PlusContractError,
    require_audio_markers,
    require_narration_bound_shot,
)
from src.application.siraj_v4_plus_attempt_ledger_v1 import (
    append_event,
    assert_submission_authorized,
)

def test_context_forbids_fixed_pre_audio_values(tmp_path):
    path = tmp_path / "context.json"
    path.write_text(json.dumps({
        "episode_id": "episode-002-test",
        "generation_id": "G2",
        "target_duration_seconds": 900
    }), encoding="utf-8")
    with pytest.raises(SirajV4PlusContractError):
        EpisodeContext.from_json(path)

def test_audio_markers_require_intro_and_outro_pauses():
    require_audio_markers({
        "hook_end_seconds": 40,
        "intro_entry_seconds": 41,
        "hook_intro_pause_seconds": 1.0,
        "final_tts_duration_seconds": 800,
        "outro_entry_seconds": 790,
        "pre_outro_pause_seconds": 0.7,
        "closing_performance_status": "PASS",
    })

def test_narration_binding_required():
    require_narration_bound_shot({
        "shot_id": "SH001",
        "narration_beat_id": "B1",
        "narration_text_ar": "نص",
        "visual_rationale_ar": "سبب",
        "semantic_alignment_status": "PASS",
        "semantic_alignment_score": 0.95,
    })

def test_retry_requires_queue_specific_authorization(tmp_path):
    path = tmp_path / "ledger.jsonl"
    append_event(path, {
        "queue_id": "Q1",
        "provider": "runware",
        "attempt_no": 1,
        "state": "AUTHORIZED",
        "authorization_id": "A1",
        "authorization_kind": "INITIAL",
    })
    assert_submission_authorized(path, "Q1", 1, "A1")
    append_event(path, {
        "queue_id": "Q1",
        "provider": "runware",
        "attempt_no": 1,
        "state": "SUBMITTED",
    })
    append_event(path, {
        "queue_id": "Q1",
        "provider": "runware",
        "attempt_no": 2,
        "state": "AUTHORIZED",
        "authorization_id": "A2",
        "authorization_kind": "QUEUE_SPECIFIC_RETRY",
    })
    assert_submission_authorized(path, "Q1", 2, "A2")
