from __future__ import annotations

from pathlib import Path

from src.application.episode_002_candidate_promotion_v1 import verify_promoted_state


def test_promoted_episode_002_state_is_exact_and_stopped_before_duplicate_gate():
    result = verify_promoted_state(Path(__file__).resolve().parents[1])
    assert result["status"] == "PASS"
    assert result["candidate_sha256"] == "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
    assert result["human_semantic_closures_committed"] == 5
    assert result["modified_creative_shots"] == 29
    assert result["unexpected_creative_shot_changes"] == 0
    assert result["gate_001"]["next_stage"] == "PROMPT_SIMILARITY_AND_DUPLICATE_GATE"
    assert result["gate_001"]["next_stage_executed"] is False
    assert result["network_calls"] == result["paid_provider_calls"] == result["autopilot_runs"] == 0
