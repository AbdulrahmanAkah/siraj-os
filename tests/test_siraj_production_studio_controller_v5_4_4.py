from pathlib import Path

from src.application.siraj_production_studio_controller_v5_4_4 import (
    EXPECTED_MODEL_ID,
    EXPECTED_PROVIDER,
    EXPECTED_VOICE_ID,
    immutable_request_manifest_sha256,
    load_dashboard_state,
)


def test_v5_studio_reads_current_final_tts_contract():
    repo = Path(__file__).resolve().parents[1]
    state = load_dashboard_state(repo)
    assert state.provider == EXPECTED_PROVIDER
    assert state.voice_id == EXPECTED_VOICE_ID
    assert state.model_id == EXPECTED_MODEL_ID
    assert state.planned_requests == 12
    assert state.total_items == 12


def test_manifest_is_deterministic():
    repo = Path(__file__).resolve().parents[1]
    import json
    queue = json.loads(
        (
            repo
            / "projects/episode-002-adam-temptation-fall-repentance/"
            "orchestration/final-tts-queue-v5-4-3.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        immutable_request_manifest_sha256(queue)
        == immutable_request_manifest_sha256(queue)
    )
