from __future__ import annotations

from src.application.adam_world_motion_repair_v2 import (
    build_narration_export,
    repair_visual_plan,
)


def _shot(shot_id: str, sequence: str, text: str, duration: int) -> dict:
    return {
        "shot_id": shot_id,
        "sequence_id": sequence,
        "visual_brief_ar": text,
        "planned_seconds": duration,
        "final_budget_treatment": "DYNAMIC_STILL_SEQUENCE",
        "motion_necessity": "OPTIONAL",
        "video_priority_v2": 65,
        "still_panel_count": 2,
        "maximum_still_panel_seconds": duration / 2,
    }


def test_sh023_becomes_video_and_world_domains_are_sequence_driven() -> None:
    storyboard = {
        "shots": [
            _shot("SH-001", "SEQ-01", "سكون رمزي", 8),
            _shot(
                "SH-023",
                "SEQ-05",
                "سطح طيني يتغير ويتشقق حتى يصير كالفخار",
                12,
            ),
            _shot("SH-024", "SEQ-06", "الحمد الأول", 8),
        ]
    }
    plan = {
        "shots": [
            dict(item, shot_id=f"P-{index:03d}")
            for index, item in enumerate(storyboard["shots"], start=1)
        ]
    }
    result = repair_visual_plan(storyboard, plan)
    shots = result.storyboard["shots"]
    assert shots[0]["scene_domain"] == "HEAVENLY_UNSEEN_SYMBOLIC"
    assert shots[1]["scene_domain"] == "EARTHLY_WORLD"
    assert shots[1]["final_budget_treatment"] == "GENERATED_VIDEO"
    assert shots[2]["scene_domain"] == "HEAVENLY_UNSEEN_SYMBOLIC"
    assert result.visual_summary["remaining_motion_required_not_video"] == []


def test_narration_export_creates_empty_tts_slots() -> None:
    payload = build_narration_export(
        {
            "segments": [
                {
                    "segment_id": "SEG-001",
                    "title_ar": "البداية",
                    "narration_ar": "هذا نص أول. وهذا نص ثان؟",
                }
            ]
        },
        "source.json",
    )
    blocks = payload["segments"][0]["performance_blocks"]
    assert blocks
    assert all(block["tts_text_ar"] is None for block in blocks)
    assert payload["status"] == (
        "AWAITING_FULL_DIACRITIZATION_AND_HUMAN_REVIEW"
    )


def test_authored_graphics_motion_does_not_require_generated_video() -> None:
    storyboard = {
        "shots": [
            {
                "shot_id": "SH-005",
                "sequence_id": "SEQ-01",
                "visual_brief_ar": "يتحول الشق إلى عنوان مصمم",
                "planned_seconds": 10,
                "final_budget_treatment": "AUTHORED_GRAPHICS",
                "motion_necessity": "OPTIONAL",
                "video_priority_v2": 65,
                "still_panel_count": 0,
                "maximum_still_panel_seconds": 0,
            },
            {
                "shot_id": "SH-033",
                "sequence_id": "SEQ-07",
                "visual_brief_ar": "تتشكل شبكة المعاني تدريجيًا",
                "planned_seconds": 12,
                "final_budget_treatment": "DYNAMIC_STILL_SEQUENCE",
                "motion_necessity": "OPTIONAL",
                "video_priority_v2": 65,
                "still_panel_count": 2,
                "maximum_still_panel_seconds": 6,
            },
            {
                "shot_id": "SH-023",
                "sequence_id": "SEQ-05",
                "visual_brief_ar": "يتغير الطين ويتشقق حتى يصير كالفخار",
                "planned_seconds": 12,
                "final_budget_treatment": "DYNAMIC_STILL_SEQUENCE",
                "motion_necessity": "OPTIONAL",
                "video_priority_v2": 65,
                "still_panel_count": 2,
                "maximum_still_panel_seconds": 6,
            },
        ]
    }
    plan = {
        "shots": [
            dict(item, shot_id=f"P-{index:03d}")
            for index, item in enumerate(storyboard["shots"], start=1)
        ]
    }
    result = repair_visual_plan(storyboard, plan)
    shots = result.storyboard["shots"]
    assert shots[0]["final_budget_treatment"] == "AUTHORED_GRAPHICS"
    assert shots[1]["final_budget_treatment"] == "GENERATED_VIDEO"
    assert shots[2]["final_budget_treatment"] == "GENERATED_VIDEO"
    assert result.visual_summary["remaining_motion_required_not_video"] == []


def test_narration_export_accepts_prestige_sequences() -> None:
    payload = build_narration_export(
        {
            "sequences": [
                {
                    "sequence_id": "ADAM-SEQUENCE-01",
                    "sequence_title": "السجدة التي لم تكتمل",
                    "narration": "انخفض كل شيء في حركة واحدة. ثم بقي موضع واحد قائمًا.",
                }
            ]
        },
        "prestige-script.json",
    )
    assert payload["source_structure"] == "sequences"
    assert payload["segments"][0]["segment_id"] == "ADAM-SEQUENCE-01"
    assert payload["segments"][0]["title_ar"] == "السجدة التي لم تكتمل"
    assert payload["segments"][0]["performance_blocks"]
