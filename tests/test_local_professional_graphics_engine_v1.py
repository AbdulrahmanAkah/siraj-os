from __future__ import annotations

from pathlib import Path

import pytest

from src.application.local_graphics_renderer_v1 import (
    TEMPLATE_BY_TYPE,
    build_ffmpeg_command,
    environment_report,
)
from src.application.local_graphics_spec_v1 import (
    FPS,
    GRAPHIC_TYPES,
    HEIGHT,
    WIDTH,
    LocalGraphicsSpecError,
    extract_storyboard_graphics_specs,
    validate_graphics_spec,
)


def _spec(index: int, shot_id: str, graphic_type: str) -> dict:
    return {
        "schema_version": "siraj-local-graphics-spec-v1",
        "graphic_id": f"GFX-{index:02d}",
        "shot_id": shot_id,
        "graphic_type": graphic_type,
        "duration_seconds": 10,
        "title_ar": "عنوان الجرافيك",
        "subtitle_ar": "شرح موجز",
        "items": [
            {
                "item_id": "GI-01",
                "label_ar": "العنصر",
                "secondary_ar": "",
                "value_ar": "القيمة",
                "source_ids": ["SRC-001"],
                "x": 0.5,
                "y": 0.5,
                "parent_item_id": "",
            }
        ],
        "source_ids": ["SRC-001"],
        "animation_style": "CINEMATIC_REVEAL",
        "background": {
            "mode": "GRADIENT",
            "image_url": "",
            "overlay_opacity": 0.1,
        },
        "design": {
            "font_family": "Segoe UI",
            "accent_hex": "#C99A45",
            "foreground_hex": "#F3EBDD",
            "background_hex": "#17130F",
            "safe_margin_px": 120,
        },
        "music": "FORBIDDEN",
        "sound_policy": "SFX_ONLY_NO_MUSIC",
    }


def test_graphics_spec_contract() -> None:
    spec = validate_graphics_spec(
        _spec(1, "SH-065", "ANIMATED_TIMELINE"),
        known_source_ids={"SRC-001"},
    )
    assert spec.frame_count == 300
    assert spec.graphic_type == "ANIMATED_TIMELINE"
    assert WIDTH == 1920
    assert HEIGHT == 1080
    assert FPS == 30


def test_music_and_unknown_sources_are_blocked() -> None:
    payload = _spec(1, "SH-065", "SOURCE_CARD")
    payload["music"] = "ALLOWED"
    with pytest.raises(LocalGraphicsSpecError):
        validate_graphics_spec(payload)

    payload = _spec(1, "SH-065", "SOURCE_CARD")
    with pytest.raises(LocalGraphicsSpecError):
        validate_graphics_spec(
            payload,
            known_source_ids={"SRC-999"},
        )


def test_storyboard_requires_exactly_six_graphics_specs() -> None:
    types = sorted(GRAPHIC_TYPES)
    shots = []
    for index in range(1, 7):
        shot_id = f"SH-{64 + index:03d}"
        shots.append(
            {
                "shot_id": shot_id,
                "final_budget_treatment": "GRAPHICS",
                "graphics_spec": _spec(
                    index,
                    shot_id,
                    types[index - 1],
                ),
            }
        )
    storyboard = {"shots": shots}
    result = extract_storyboard_graphics_specs(
        storyboard,
        known_source_ids={"SRC-001"},
    )
    assert len(result) == 6


def test_non_graphics_shot_must_have_null_spec() -> None:
    storyboard = {
        "shots": [
            {
                "shot_id": "SH-001",
                "final_budget_treatment": "GENERATED_VIDEO",
                "graphics_spec": _spec(
                    1,
                    "SH-001",
                    "SOURCE_CARD",
                ),
            }
        ]
    }
    with pytest.raises(LocalGraphicsSpecError):
        extract_storyboard_graphics_specs(storyboard)


def test_ffmpeg_command_is_1080p_sequence_to_h264(tmp_path: Path) -> None:
    command = build_ffmpeg_command(
        Path("ffmpeg"),
        tmp_path / "frames",
        tmp_path / "out.mp4",
    )
    assert "-framerate" in command
    assert "30" in command
    assert "libx264" in command
    assert "yuv420p" in command
    assert "frame_%06d.png" in " ".join(command)


def test_all_qml_templates_are_present() -> None:
    root = Path("src/presentation/graphics/qml")
    assert set(TEMPLATE_BY_TYPE) == GRAPHIC_TYPES
    for filename in TEMPLATE_BY_TYPE.values():
        source = (root / filename).read_text(encoding="utf-8")
        assert "property real frameProgress" in source
        assert "graphicsSpec.design.font_family" in source
        assert "1920" in source and "1080" in source


def test_environment_report_is_non_destructive(tmp_path: Path) -> None:
    report = environment_report(tmp_path)
    assert report["release"] == (
        "LOCAL_PROFESSIONAL_GRAPHICS_ENGINE_V1"
    )
    assert "ffmpeg_ready" in report
    assert "render_ready" in report
