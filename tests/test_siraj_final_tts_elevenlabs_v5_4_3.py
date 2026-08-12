from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.siraj_final_tts_elevenlabs_v5_4_3 import (
    MODEL_ID,
    OUTPUT_FORMAT,
    PROVIDER,
    VOICE_ID,
    VOICE_SETTINGS,
    FinalTtsError,
    _authorization,
    _queue,
)


def test_locked_episode1_primary_narrator_contract():
    assert PROVIDER == "ELEVENLABS"
    assert VOICE_ID == "XdoLPWNt7ytn6BtU4FBf"
    assert MODEL_ID == "eleven_multilingual_v2"
    assert OUTPUT_FORMAT == "mp3_44100_128"
    assert VOICE_SETTINGS == {
        "stability": 0.38,
        "similarity_boost": 0.75,
        "style": 0.42,
        "use_speaker_boost": True,
    }


def test_queue_has_no_assistant_authored_cost_cap(repo_root):
    queue = _queue(repo_root)
    assert queue["assistant_authored_cost_cap_usd"] is None
    assert queue["automatic_retry"] is False
    assert queue["status"] == "AWAITING_EXPLICIT_PAID_AUTHORIZATION"


def test_execution_is_blocked_without_paid_authorization(repo_root):
    queue = _queue(repo_root)
    auth = repo_root / (
        "projects/episode-002-adam-temptation-fall-repentance/"
        "orchestration/final-tts-paid-authorization-v5-4-3.json"
    )
    if auth.exists():
        pytest.skip("Authorization already exists in this checkout.")
    with pytest.raises(
        FinalTtsError,
        match="EXPLICIT_FINAL_TTS_PAID_AUTHORIZATION_REQUIRED",
    ):
        _authorization(repo_root, queue)


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parents[1]
