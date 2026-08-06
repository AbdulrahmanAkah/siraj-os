from __future__ import annotations

from src.application.series_production_standard_v2_repair import (
    _contains_camera_metadata,
    repaired_planned_generated_video_spend,
)


def test_recursive_camera_metadata_detector() -> None:
    shot = {
        "camera_plan_v2": {
            "lens_family": "32_TO_50MM",
            "camera_movement": "CONTROLLED_DOLLY",
        }
    }
    assert _contains_camera_metadata(shot) is True


def test_nested_budget_discovery() -> None:
    plan = {
        "generated_video_budget": {
            "estimated_spend_usd": 29.514375,
        },
        "shots": [],
    }
    assert repaired_planned_generated_video_spend(
        plan,
        {},
    ) == 29.514375


def test_sum_budget_fallback() -> None:
    plan = {
        "shots": [
            {
                "final_budget_treatment": "GENERATED_VIDEO",
                "estimated_generated_video_cost_usd": 1.25,
            },
            {
                "final_budget_treatment": "AUTHORED_GRAPHICS",
                "estimated_generated_video_cost_usd": 0.0,
            },
            {
                "final_budget_treatment": "GENERATED_VIDEO",
                "estimated_generated_video_cost_usd": 0.75,
            },
        ]
    }
    assert repaired_planned_generated_video_spend(
        plan,
        {},
    ) == 2.0
