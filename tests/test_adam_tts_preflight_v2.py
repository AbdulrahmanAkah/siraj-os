from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.adam_tts_preflight_v2 import (
    SAMPLE_BLOCK_ID,
    build_preflight,
)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    assert isinstance(value, dict)
    return value


def test_adam_tts_preflight_is_offline_and_selects_primary_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    episode = repo / "projects/episode-001-adam"

    monkeypatch.setattr(
        "src.application.adam_tts_preflight_v2.read_elevenlabs_api_key",
        lambda: None,
    )

    result = build_preflight(
        repo=repo,
        episode_id="episode-001-adam",
        script=load_json(episode / "script/episode-script-v2.json"),
        storyboard=load_json(
            episode / "cinematic/storyboard-and-media-plan-v2.json"
        ),
    )

    preflight = result["preflight"]
    sample = result["sample_request"]
    cast = result["cast_plan"]

    assert preflight["provider_requests"] == 0
    assert preflight["paid_provider_requests"] == 0
    assert preflight["sample_generation_authorized"] is False
    assert preflight["script"]["performance_block_count"] == 43
    assert cast["performer_slots_used"] == ["PRIMARY"]
    assert sample["block_id"] == SAMPLE_BLOCK_ID
    assert sample["voice_slot"] == "PRIMARY"
    assert sample["explicit_paid_authorization_required"] is True
    assert sample["suggested_authorization_ceiling_usd"] > 0
    assert sample["suggested_authorization_ceiling_usd"] <= 0.25
