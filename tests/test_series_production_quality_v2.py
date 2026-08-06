from __future__ import annotations

import pytest

from src.application.budget_driven_media_planner_v2 import (
    MediaOptionV2,
    plan_media,
)
from src.application.series_production_quality_v2 import (
    EpisodeVideoSpend,
    SeriesProductionPolicyV2,
    assert_tts_text_ready,
    rolling_budget_snapshot,
)


def test_policy_defaults_are_locked() -> None:
    policy = SeriesProductionPolicyV2()
    policy.validate()
    assert policy.budget.target_generated_video_spend_usd == 30.0
    assert policy.budget.hard_generated_video_spend_usd == 35.0
    assert policy.visual.generated_video_seconds_target == (
        "NONE_COST_AND_QUALITY_DRIVEN"
    )


def test_rolling_five_episode_target() -> None:
    snapshot = rolling_budget_snapshot(
        [
            EpisodeVideoSpend("e1", 33.0),
            EpisodeVideoSpend("e2", 29.0),
            EpisodeVideoSpend("e3", 31.0),
            EpisodeVideoSpend("e4", 27.0),
            EpisodeVideoSpend("e5", 30.0),
        ]
    )
    assert snapshot.generated_video_spend_usd == 150.0
    assert snapshot.average_usd == 30.0
    assert snapshot.compliant is True


def test_unvocalized_tts_is_blocked() -> None:
    with pytest.raises(Exception):
        assert_tts_text_ready("هذا نص عربي غير مشكل بالكامل")


def test_budget_planner_prefers_video_for_required_motion() -> None:
    shots = [
        {
            "shot_id": "s1",
            "motion_necessity": "REQUIRED",
            "label_ar": "يتكوّن الطين تدريجيًا",
        },
        {
            "shot_id": "s2",
            "scene_domain": "DOCUMENTARY_EVIDENCE",
        },
    ]
    options = [
        MediaOptionV2(
            "s1-image",
            "s1",
            "DYNAMIC_STILL",
            0.1,
            90,
            90,
            visual_fit_score=70,
            continuity_score=80,
        ),
        MediaOptionV2(
            "s1-video",
            "s1",
            "GENERATED_VIDEO",
            1.0,
            85,
            85,
            generated_video_seconds=8,
            visual_fit_score=95,
            continuity_score=90,
        ),
        MediaOptionV2(
            "s2-document",
            "s2",
            "DOCUMENT",
            0.0,
            90,
            100,
            visual_fit_score=95,
            continuity_score=95,
        ),
    ]
    plan = plan_media(shots, options)
    assert plan.selected[0].option_id == "s1-video"
    assert plan.generated_video_spend_usd == 1.0
