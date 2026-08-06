from __future__ import annotations

from src.application.adam_visual_replan_v2 import build_adam_visual_replan


def test_replan_adds_world_fields_and_respects_budget() -> None:
    storyboard = {
        "shots": [
            {"shot_id": "SH-001", "label_ar": "الطين يتكوّن", "planned_seconds": 8},
            {"shot_id": "SH-002", "label_ar": "وثيقة", "planned_seconds": 12},
            {"shot_id": "SH-003", "label_ar": "مشهد هادئ", "planned_seconds": 12},
        ]
    }
    plan = {
        "shots": [
            {
                "shot_id": "P-001",
                "editorial_duration_seconds": 8,
                "scene_domain": "EARTHLY_WORLD",
                "character_location": "NONE",
                "representation_mode": "EVIDENCE_BASED_RECONSTRUCTION",
                "representation_claim": "EVIDENCE_BASED",
                "motion_necessity": "REQUIRED",
                "video_priority_v2": 100,
                "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
            },
            {
                "shot_id": "P-002",
                "editorial_duration_seconds": 12,
                "scene_domain": "DOCUMENTARY_EVIDENCE",
                "character_location": "NONE",
                "representation_mode": "DOCUMENTARY",
                "representation_claim": "DOCUMENTARY",
                "motion_necessity": "OPTIONAL",
                "video_priority_v2": 20,
                "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
            },
            {
                "shot_id": "P-003",
                "editorial_duration_seconds": 12,
                "scene_domain": "HEAVENLY_UNSEEN_SYMBOLIC",
                "character_location": "ADAM_IN_HEAVEN",
                "representation_mode": "SYMBOLIC_UNSEEN",
                "representation_claim": "SYMBOLIC_NON_DEFINITIVE",
                "motion_necessity": "OPTIONAL",
                "video_priority_v2": 80,
                "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
            },
        ]
    }
    result = build_adam_visual_replan(
        storyboard,
        plan,
        cost_per_second_usd=0.1,
        target_usd=2.0,
        hard_usd=3.0,
    )
    assert result.storyboard["shots"][0]["final_budget_treatment"] == "GENERATED_VIDEO"
    assert result.storyboard["shots"][1]["final_budget_treatment"] == "DOCUMENT_OR_MAP"
    assert all(shot["scene_domain"] for shot in result.storyboard["shots"])
    assert result.summary["generated_video"]["estimated_spend_usd"] <= 2.0
    assert result.summary["required_motion_not_video"] == []
