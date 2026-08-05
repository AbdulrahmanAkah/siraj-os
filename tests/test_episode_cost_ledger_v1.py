from __future__ import annotations

import json
from pathlib import Path

from src.application.episode_cost_ledger_v1 import scan_episode_costs


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_episode_cost_breakdown_classifies_and_deduplicates(tmp_path: Path) -> None:
    root = tmp_path / "projects" / "episode-001-adam"

    _write(
        root / "video" / "execution-receipt-v1.json",
        {
            "provider": "RUNWARE",
            "task_type": "videoInference",
            "task_uuid": "same-task",
            "actual_cost_usd": 0.40,
        },
    )
    _write(
        root / "video" / "duplicate-receipt-v1.json",
        {
            "provider": "RUNWARE",
            "task_type": "videoInference",
            "task_uuid": "same-task",
            "actual_cost_usd": 0.40,
        },
    )
    _write(
        root / "images" / "image-receipt-v1.json",
        {
            "provider": "RUNWARE",
            "media_type": "IMAGE",
            "task_uuid": "image-task",
            "actual_cost_usd": 0.10,
        },
    )
    _write(
        root / "tts" / "elevenlabs-receipt-v1.json",
        {
            "provider": "ELEVENLABS",
            "cost_category": "ELEVENLABS_TTS",
            "receipt_id": "tts-1",
            "estimated_cost_usd": 0.20,
        },
    )
    _write(
        root / "sfx" / "sfx-receipt-v1.json",
        {
            "cost_category": "SOUND_EFFECTS",
            "receipt_id": "sfx-1",
            "actual_cost_usd": 0.05,
        },
    )
    _write(
        root / "misc" / "other-receipt-v1.json",
        {
            "receipt_id": "other-1",
            "actual_cost_usd": 0.03,
        },
    )

    result = scan_episode_costs(tmp_path, "episode-001-adam")
    by_key = {item.category: item for item in result.categories}

    assert result.actual_cost_usd == 0.58
    assert result.estimated_cost_usd == 0.20
    assert result.recorded_total_usd == 0.78
    assert result.remaining_usd == 39.22
    assert result.paid_operations == 5
    assert result.unclassified_operations == 1
    assert by_key["RUNWARE_VIDEO"].actual_cost_usd == 0.40
    assert by_key["RUNWARE_IMAGES"].actual_cost_usd == 0.10
    assert by_key["ELEVENLABS_TTS"].estimated_cost_usd == 0.20
    assert by_key["SOUND_EFFECTS"].actual_cost_usd == 0.05
    assert by_key["OTHER"].actual_cost_usd == 0.03


def test_active_episode_is_read_from_orchestrator_state(tmp_path: Path) -> None:
    state = (
        tmp_path
        / "projects"
        / "_orchestrator"
        / "autonomous-episode-orchestrator-state-v1.json"
    )
    _write(
        state,
        {
            "current_episode_id": "episode-002-test",
            "active_scope_luna_usage": {
                "estimated_text_cost_usd": 0.0123,
            },
        },
    )
    _write(
        tmp_path
        / "projects"
        / "episode-002-test"
        / "orchestration"
        / "cost-receipts"
        / "openai-luna-scope-receipt-v1.json",
        {
            "provider": "OPENAI",
            "cost_category": "OPENAI_LUNA",
            "provider_response_id": "resp-1",
            "estimated_cost_usd": 0.05,
        },
    )

    result = scan_episode_costs(tmp_path)
    assert result.episode_id == "episode-002-test"
    assert result.estimated_cost_usd == 0.05
    assert result.pending_scope_estimated_usd == 0.0123
