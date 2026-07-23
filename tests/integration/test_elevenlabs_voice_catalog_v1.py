from __future__ import annotations

from src.application.local_video_production.elevenlabs_voice_catalog_v1 import (
    calculate_narration_score,
    parse_voice_candidate,
)


def test_documentary_voice_scores_higher() -> None:
    documentary = {
        "voice_id": "voice-1",
        "name": "Narrator",
        "category": "professional",
        "description": (
            "Calm documentary narration"
        ),
        "labels": {
            "use_case": "narration",
            "age": "middle-aged",
        },
    }

    social = {
        "voice_id": "voice-2",
        "name": "Social",
        "category": "generated",
        "description": (
            "Energetic social media voice"
        ),
        "labels": {
            "use_case": "social media",
        },
    }

    assert calculate_narration_score(
        documentary
    ) > calculate_narration_score(
        social
    )


def test_candidate_parses_labels() -> None:
    candidate = parse_voice_candidate(
        {
            "voice_id": "voice-1",
            "name": "Test Voice",
            "category": "professional",
            "description": "Calm narrator",
            "labels": {
                "gender": "male",
                "age": "middle-aged",
                "accent": "neutral",
                "use_case": "narration",
            },
            "available_for_tiers": [
                "free",
                "starter",
            ],
            "preview_url": (
                "https://example.invalid/"
                "preview.mp3"
            ),
        }
    )

    assert candidate.voice_id == "voice-1"
    assert candidate.gender == "male"
    assert candidate.available_for_free is True
    assert candidate.narration_score > 0