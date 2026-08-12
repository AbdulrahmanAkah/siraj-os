from src.application.siraj_visual_mix_policy_v6_2_1 import (
    MAX_GENERATED_VIDEO_RATIO,
    MIN_NON_GENERATED_VIDEO_RATIO,
    PROVIDER_REQUEST_FALLBACK_MAX_SECONDS,
)
from src.application.siraj_duplicate_gates_v6_2_1 import (
    validate_pre_spend_duplicates,
    perceptually_near_duplicate,
)


def test_two_thirds_policy_exact():
    assert abs(MAX_GENERATED_VIDEO_RATIO - (2 / 3)) < 1e-12
    assert abs(MIN_NON_GENERATED_VIDEO_RATIO - (1 / 3)) < 1e-12


def test_eight_seconds_is_transport_fallback_not_scene_limit():
    assert PROVIDER_REQUEST_FALLBACK_MAX_SECONDS == 8.0


def test_identical_prompt_detected():
    items = [
        {
            "shot_id": "A",
            "runware_positive_prompt_en": (
                "wide desert dawn cinematic tracking"
            ),
            "semantic_beat": "arrival",
        },
        {
            "shot_id": "B",
            "runware_positive_prompt_en": (
                "wide desert dawn cinematic tracking"
            ),
            "semantic_beat": "different event",
        },
    ]
    problems = validate_pre_spend_duplicates(items)
    assert any(
        p["type"] == "PROMPT_NEAR_DUPLICATE"
        for p in problems
    )


def test_obvious_perceptual_duplicate_detected():
    a = (0, 0, 0)
    duplicate, average, maximum = perceptually_near_duplicate(
        a,
        a,
    )
    assert duplicate is True
    assert average == 0
    assert maximum == 0
