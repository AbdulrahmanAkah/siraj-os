"""Episode render manifest v2 and timed-scene contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EPISODE_RENDER_MANIFEST_V2 = (
    "siraj-episode-render-manifest-v2"
)

ALLOWED_MOTIONS = {
    "STATIC",
    "PUSH_IN",
    "PULL_OUT",
    "PAN_LEFT_TO_RIGHT",
    "PAN_RIGHT_TO_LEFT",
    "PARALLAX",
    "MAP_ANIMATION",
    "SOURCE_CARD",
}

ALLOWED_TRANSITIONS = {
    "CUT",
    "FADE",
    "DISSOLVE",
    "WIPE_LEFT",
    "WIPE_RIGHT",
    "DIP_TO_BLACK",
}

ALLOWED_SUBTITLE_MODES = {
    "NONE",
    "SIDECAR",
    "BURNED_IN",
}

ALLOWED_AUDIO_ROLES = {
    "NARRATION",
    "AMBIENCE",
    "EFFECT",
    "ROOM_TONE",
    "SCORE",
}


@dataclass(frozen=True)
class TimedScene:
    scene_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    visual_asset_path: str
    motion: str
    transition: str
    claim_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    visual_policy_refs: tuple[str, ...]


def _validate_reference_list(
    scene_id: str,
    field: str,
    value: Any,
) -> None:
    if (
        not isinstance(value, list)
        or not value
        or not all(
            isinstance(item, str)
            and item.strip()
            for item in value
        )
    ):
        raise ValueError(
            f"SCENE_REFERENCE_INVALID:"
            f"{scene_id}:{field}"
        )


def validate_episode_render_manifest_v2(
    manifest: dict[str, Any],
) -> None:
    if (
        manifest.get("schema_version")
        != EPISODE_RENDER_MANIFEST_V2
    ):
        raise ValueError(
            "EPISODE_RENDER_V2_SCHEMA_INVALID"
        )

    if not str(
        manifest.get("episode_id", "")
    ).strip():
        raise ValueError("EPISODE_ID_REQUIRED")

    scenes = manifest.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        raise ValueError("TIMED_SCENES_REQUIRED")

    previous_end = 0
    seen_scene_ids: set[str] = set()

    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ValueError(
                f"SCENE_INVALID:{index}"
            )

        scene_id = str(
            scene.get("scene_id", "")
        ).strip()

        if not scene_id:
            raise ValueError(
                f"SCENE_ID_REQUIRED:{index}"
            )

        if scene_id in seen_scene_ids:
            raise ValueError(
                f"SCENE_ID_DUPLICATE:{scene_id}"
            )

        seen_scene_ids.add(scene_id)

        start_ms = scene.get("start_ms")
        end_ms = scene.get("end_ms")
        duration_ms = scene.get("duration_ms")

        if (
            not isinstance(start_ms, int)
            or not isinstance(end_ms, int)
            or not isinstance(duration_ms, int)
            or start_ms < 0
            or end_ms <= start_ms
            or duration_ms != end_ms - start_ms
        ):
            raise ValueError(
                f"SCENE_TIMING_INVALID:{scene_id}"
            )

        if start_ms < previous_end:
            raise ValueError(
                f"SCENE_OVERLAP:{scene_id}"
            )

        previous_end = end_ms

        if not str(
            scene.get(
                "visual_asset_path",
                "",
            )
        ).strip():
            raise ValueError(
                f"SCENE_VISUAL_REQUIRED:{scene_id}"
            )

        if (
            scene.get("motion", "STATIC")
            not in ALLOWED_MOTIONS
        ):
            raise ValueError(
                f"SCENE_MOTION_INVALID:{scene_id}"
            )

        if (
            scene.get("transition", "CUT")
            not in ALLOWED_TRANSITIONS
        ):
            raise ValueError(
                f"SCENE_TRANSITION_INVALID:{scene_id}"
            )

        for field in (
            "claim_ids",
            "source_ids",
            "visual_policy_refs",
        ):
            _validate_reference_list(
                scene_id,
                field,
                scene.get(field),
            )

    audio_layers = manifest.get(
        "audio_layers"
    )

    if (
        not isinstance(audio_layers, list)
        or not audio_layers
    ):
        raise ValueError("AUDIO_LAYERS_REQUIRED")

    narration_count = 0
    seen_layer_ids: set[str] = set()

    for index, layer in enumerate(
        audio_layers
    ):
        if not isinstance(layer, dict):
            raise ValueError(
                f"AUDIO_LAYER_INVALID:{index}"
            )

        layer_id = str(
            layer.get("layer_id", "")
        ).strip()

        if not layer_id:
            raise ValueError(
                f"AUDIO_LAYER_ID_REQUIRED:{index}"
            )

        if layer_id in seen_layer_ids:
            raise ValueError(
                f"AUDIO_LAYER_ID_DUPLICATE:{layer_id}"
            )

        seen_layer_ids.add(layer_id)

        role = layer.get("role")

        if role not in ALLOWED_AUDIO_ROLES:
            raise ValueError(
                f"AUDIO_ROLE_INVALID:{index}"
            )

        if role == "NARRATION":
            narration_count += 1

        if not str(
            layer.get("path", "")
        ).strip():
            raise ValueError(
                f"AUDIO_PATH_REQUIRED:{index}"
            )

        if not isinstance(
            layer.get("start_ms", 0),
            int,
        ):
            raise ValueError(
                f"AUDIO_START_INVALID:{index}"
            )

        if not isinstance(
            layer.get("gain_db", 0),
            (int, float),
        ):
            raise ValueError(
                f"AUDIO_GAIN_INVALID:{index}"
            )

    if narration_count != 1:
        raise ValueError(
            "EXACTLY_ONE_NARRATION_LAYER_REQUIRED"
        )

    subtitles = manifest.get(
        "subtitles",
        {},
    )

    if not isinstance(subtitles, dict):
        raise ValueError(
            "SUBTITLE_CONFIGURATION_INVALID"
        )

    mode = subtitles.get("mode", "NONE")

    if mode not in ALLOWED_SUBTITLE_MODES:
        raise ValueError(
            "SUBTITLE_MODE_INVALID"
        )

    if (
        mode != "NONE"
        and not str(
            subtitles.get("path", "")
        ).strip()
    ):
        raise ValueError(
            "SUBTITLE_PATH_REQUIRED"
        )

    output = manifest.get("output")

    if (
        not isinstance(output, dict)
        or not str(
            output.get("video", "")
        ).strip()
        or not str(
            output.get("report", "")
        ).strip()
    ):
        raise ValueError(
            "EPISODE_OUTPUT_REQUIRED"
        )


def build_timed_scene_plan(
    scene_specs: list[dict[str, Any]],
) -> list[TimedScene]:
    if not scene_specs:
        raise ValueError("SCENE_SPECS_REQUIRED")

    result: list[TimedScene] = []
    cursor_ms = 0

    for index, spec in enumerate(
        scene_specs,
        start=1,
    ):
        duration_ms = spec.get(
            "duration_ms"
        )

        if (
            not isinstance(duration_ms, int)
            or duration_ms <= 0
        ):
            raise ValueError(
                f"SCENE_DURATION_INVALID:{index}"
            )

        scene_id = str(
            spec.get(
                "scene_id",
                f"scene-{index:03d}",
            )
        )

        scene = TimedScene(
            scene_id=scene_id,
            start_ms=cursor_ms,
            end_ms=cursor_ms + duration_ms,
            duration_ms=duration_ms,
            visual_asset_path=str(
                spec["visual_asset_path"]
            ),
            motion=str(
                spec.get(
                    "motion",
                    "STATIC",
                )
            ),
            transition=str(
                spec.get(
                    "transition",
                    "CUT",
                )
            ),
            claim_ids=tuple(
                spec["claim_ids"]
            ),
            source_ids=tuple(
                spec["source_ids"]
            ),
            visual_policy_refs=tuple(
                spec["visual_policy_refs"]
            ),
        )

        result.append(scene)
        cursor_ms = scene.end_ms

    return result