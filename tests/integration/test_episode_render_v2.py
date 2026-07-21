from __future__ import annotations

import copy

import pytest

from src.application.local_video_production.episode_render_v2 import (
    EPISODE_RENDER_MANIFEST_V2,
    build_timed_scene_plan,
    validate_episode_render_manifest_v2,
)


def sample_manifest() -> dict:
    return {
        "schema_version": (
            EPISODE_RENDER_MANIFEST_V2
        ),
        "episode_id": "episode-test",
        "scenes": [
            {
                "scene_id": "scene-001",
                "start_ms": 0,
                "end_ms": 3000,
                "duration_ms": 3000,
                "visual_asset_path": (
                    "assets/one.png"
                ),
                "motion": "PUSH_IN",
                "transition": "FADE",
                "claim_ids": ["claim-1"],
                "source_ids": ["source-1"],
                "visual_policy_refs": [
                    "policy-1"
                ],
            },
            {
                "scene_id": "scene-002",
                "start_ms": 3000,
                "end_ms": 8000,
                "duration_ms": 5000,
                "visual_asset_path": (
                    "assets/two.png"
                ),
                "motion": (
                    "PAN_LEFT_TO_RIGHT"
                ),
                "transition": "DISSOLVE",
                "claim_ids": ["claim-2"],
                "source_ids": ["source-2"],
                "visual_policy_refs": [
                    "policy-2"
                ],
            },
        ],
        "audio_layers": [
            {
                "layer_id": "narration",
                "role": "NARRATION",
                "path": "audio/narration.wav",
                "start_ms": 0,
                "gain_db": 0,
            },
            {
                "layer_id": "ambience",
                "role": "AMBIENCE",
                "path": "audio/room.wav",
                "start_ms": 0,
                "gain_db": -26,
            },
        ],
        "subtitles": {
            "mode": "SIDECAR",
            "path": "subtitles/ar.srt",
        },
        "output": {
            "video": "exports/test.mp4",
            "report": (
                "manifests/test-report.json"
            ),
        },
    }


def test_episode_render_v2_accepts_valid_manifest() -> None:
    validate_episode_render_manifest_v2(
        sample_manifest()
    )


def test_timed_scene_planner_builds_contiguous_timing() -> None:
    scenes = build_timed_scene_plan(
        [
            {
                "scene_id": "one",
                "duration_ms": 2500,
                "visual_asset_path": (
                    "assets/one.png"
                ),
                "claim_ids": ["c1"],
                "source_ids": ["s1"],
                "visual_policy_refs": ["p1"],
            },
            {
                "scene_id": "two",
                "duration_ms": 4000,
                "visual_asset_path": (
                    "assets/two.png"
                ),
                "claim_ids": ["c2"],
                "source_ids": ["s2"],
                "visual_policy_refs": ["p2"],
            },
        ]
    )

    assert scenes[0].start_ms == 0
    assert scenes[0].end_ms == 2500
    assert scenes[1].start_ms == 2500
    assert scenes[1].end_ms == 6500


def test_episode_render_v2_rejects_scene_overlap() -> None:
    manifest = sample_manifest()
    manifest["scenes"][1]["start_ms"] = 2500
    manifest["scenes"][1]["duration_ms"] = 5500

    with pytest.raises(
        ValueError,
        match="SCENE_OVERLAP",
    ):
        validate_episode_render_manifest_v2(
            manifest
        )


def test_episode_render_v2_requires_references() -> None:
    manifest = sample_manifest()
    manifest["scenes"][0]["source_ids"] = []

    with pytest.raises(
        ValueError,
        match="SCENE_REFERENCE_INVALID",
    ):
        validate_episode_render_manifest_v2(
            manifest
        )


def test_episode_render_v2_requires_one_narration() -> None:
    manifest = sample_manifest()

    duplicate = copy.deepcopy(
        manifest["audio_layers"][0]
    )
    duplicate["layer_id"] = "narration-two"

    manifest["audio_layers"].append(
        duplicate
    )

    with pytest.raises(
        ValueError,
        match=(
            "EXACTLY_ONE_NARRATION_LAYER_REQUIRED"
        ),
    ):
        validate_episode_render_manifest_v2(
            manifest
        )


def test_episode_render_v2_supports_burned_subtitles() -> None:
    manifest = sample_manifest()

    manifest["subtitles"] = {
        "mode": "BURNED_IN",
        "path": "subtitles/ar.ass",
    }

    validate_episode_render_manifest_v2(
        manifest
    )