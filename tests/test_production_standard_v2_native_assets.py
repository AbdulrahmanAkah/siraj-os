from pathlib import Path

from src.application.production_standard_v2_native_assets import (
    EXPECTED_GRAPHICS,
    EXPECTED_STILL_PANELS,
    EXPECTED_VIDEO_CLIPS,
    build_native_asset_plan,
    inspect_native_execution_plan,
)


def test_native_v2_asset_plan_matches_director_plan() -> None:
    plan = build_native_asset_plan(Path.cwd())
    assert plan["shot_count"] == 70
    assert plan["treatment_counts"] == {
        "GENERATED_VIDEO": 50,
        "DYNAMIC_STILL_SEQUENCE": 14,
        "AUTHORED_GRAPHICS": 6,
    }
    assert plan["asset_counts"]["runware_videos"] == (
        EXPECTED_VIDEO_CLIPS
    )
    assert plan["asset_counts"]["runware_images"] == (
        EXPECTED_STILL_PANELS
    )
    assert plan["asset_counts"]["local_graphics"] == (
        EXPECTED_GRAPHICS
    )
    assert plan["asset_counts"]["elevenlabs_tts"] == 43
    assert plan["timeline"]["episode_seconds"] == 1320.0
    assert plan["timeline"]["generated_video_seconds"] == 891.0
    assert plan["budget"][
        "consolidated_maximum_authorized_usd"
    ] < 40.0


def test_all_provider_assets_have_luna_supervised_certification() -> None:
    plan = build_native_asset_plan(Path.cwd())
    for collection in ("runware_images", "runware_videos"):
        for item in plan["queues"][collection]:
            certification = item[
                "luna_prompt_certification_v2"
            ]
            assert certification["status"] == "PASS"
            assert certification["asset_derivation"][
                "no_new_creative_decision"
            ] is True
            assert certification["positive_prompt_sha256"]
            assert certification["asset_derivation"][
                "master_luna_response_id"
            ]


def test_live_native_execution_plan_is_below_hard_cap() -> None:
    plan = inspect_native_execution_plan(Path.cwd())
    assert plan["counts"]["runware_images"] == 61
    assert plan["counts"]["runware_videos"] == 137
    assert plan["counts"]["local_graphics"] == 6
    assert plan["counts"]["elevenlabs_tts_segments"] == 43
    assert plan["consolidated_maximum_usd"] < 40.0
