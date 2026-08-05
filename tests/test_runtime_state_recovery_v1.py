from __future__ import annotations

import json
from pathlib import Path

from src.application.runtime_state_recovery_v1 import (
    diagnose_runtime_state,
    recover_runtime_state_from_artifacts,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def state_path(repo: Path) -> Path:
    return repo / "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"


def test_recovers_stale_qa_state_from_final_master(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    episode = repo / "projects/episode-001-test"
    final = episode / "deliverables/episode-master-v1.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"video")
    write_json(
        state_path(repo),
        {
            "current_episode_id": "episode-001-test",
            "status": "AUTOMATIC_QA_ACTIVE",
            "stage": "AUTOMATIC_QA",
        },
    )
    diagnosis = diagnose_runtime_state(repo)
    assert diagnosis.needs_recovery is True
    assert diagnosis.inferred_status == "FINAL_RENDER_READY_FOR_QA"
    assert diagnosis.inferred_action == "RUN_QA"
    result = recover_runtime_state_from_artifacts(repo)
    assert result.changed is True
    assert result.backup_path is not None and result.backup_path.is_file()
    recovered = json.loads(state_path(repo).read_text(encoding="utf-8"))
    assert recovered["status"] == "FINAL_RENDER_READY_FOR_QA"
    assert recovered["stage"] == "AUTOMATIC_QA"


def test_recovers_stale_media_state_with_pending_queue(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    episode = repo / "projects/episode-001-test"
    write_json(
        state_path(repo),
        {
            "current_episode_id": "episode-001-test",
            "status": "DESKTOP_MEDIA_EXECUTION_ACTIVE",
            "stage": "DESKTOP_MEDIA_EXECUTION",
        },
    )
    write_json(
        episode / "orchestration/media-production-queue-v1.json",
        {
            "queues": {
                "runware_images": [
                    {"queue_id": "IMG-001", "status": "PENDING"}
                ],
                "runware_videos": [],
                "local_graphics": [],
                "elevenlabs_tts": [],
            }
        },
    )
    result = recover_runtime_state_from_artifacts(repo)
    assert result.changed is True
    assert result.recovered_status == "MEDIA_QUEUE_READY"
    assert result.recovered_action == "OPEN_MEDIA_EXECUTION"


def test_valid_human_gate_is_not_rewritten(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    episode = repo / "projects/episode-001-test"
    episode.mkdir(parents=True, exist_ok=True)
    write_json(
        state_path(repo),
        {
            "current_episode_id": "episode-001-test",
            "status": "AWAITING_HUMAN_SCOPE_REVIEW",
            "stage": "HUMAN_SCOPE_REVIEW",
        },
    )
    diagnosis = diagnose_runtime_state(repo)
    assert diagnosis.needs_recovery is False
    result = recover_runtime_state_from_artifacts(repo)
    assert result.changed is False
