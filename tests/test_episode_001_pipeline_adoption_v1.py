from __future__ import annotations

from src.application.episode_001_pipeline_adoption_v1 import (
    run_episode_001_adoption_smoke_test,
)


def test_episode_001_adoption_builds_current_pipeline(tmp_path):
    result = run_episode_001_adoption_smoke_test(tmp_path)
    assert result["status"] == "PASS"
    assert result["current_episode_id"] == "episode-001-adam"
    assert result["orchestrator_status"] == "MEDIA_QUEUE_READY"
    assert result["images"] == 44
    assert result["videos"] == 20
    assert result["graphics"] == 6
    assert result["tts"] == 14
    assert result["provider_requests"] == 0
    assert result["legacy_files_preserved"] is True
