from __future__ import annotations

from src.application.local_video_production.edge_speech_provider_v1 import (
    EDGE_SPEECH_PROVIDER_ID,
    _percentage,
)


def test_provider_id_is_stable() -> None:
    assert EDGE_SPEECH_PROVIDER_ID == (
        "edge-speech-v1"
    )


def test_default_speed_percentage() -> None:
    assert _percentage(1.0) == "+0%"


def test_faster_speed_percentage() -> None:
    assert _percentage(1.15) == "+15%"


def test_slower_speed_percentage() -> None:
    assert _percentage(0.9) == "-10%"