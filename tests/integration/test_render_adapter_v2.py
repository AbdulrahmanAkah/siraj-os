from __future__ import annotations

from pathlib import Path

import pytest

from src.application.local_video_production.render_adapter_v2 import (
    _build_audio_filters,
    _motion_filter,
    _subtitle_filter,
    _transition_filters,
)


def test_motion_filter_uses_scene_duration() -> None:
    result = _motion_filter(
        input_index=0,
        motion="PAN_LEFT_TO_RIGHT",
        width=1920,
        height=1080,
        fps=24,
        duration_seconds=7.1,
    )

    assert "t/7.100000" in result
    assert "trim=duration=7.100000" in result
    assert "[scene0]" in result


def test_push_in_motion_uses_zoompan() -> None:
    result = _motion_filter(
        input_index=1,
        motion="PUSH_IN",
        width=1920,
        height=1080,
        fps=24,
        duration_seconds=5.8,
    )

    assert "zoompan=" in result
    assert "s=1920x1080" in result
    assert "[scene1]" in result


def test_cut_transition_does_not_add_fade() -> None:
    result = _transition_filters(
        label="scene0",
        transition="CUT",
        duration_seconds=5.0,
    )

    assert result == "[scene0]null[scene0out]"


def test_dip_to_black_adds_two_fades() -> None:
    result = _transition_filters(
        label="scene1",
        transition="DIP_TO_BLACK",
        duration_seconds=6.0,
    )

    assert "fade=t=in" in result
    assert "fade=t=out" in result
    assert "color=black" in result


def test_audio_filters_support_multiple_layers() -> None:
    layers = [
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
            "path": "audio/ambience.wav",
            "start_ms": 250,
            "gain_db": -30,
        },
    ]

    filters, output = _build_audio_filters(
        audio_layers=layers,
        first_audio_input=3,
        total_duration_seconds=19.402,
    )

    joined = ";".join(filters)

    assert "[3:a]" in joined
    assert "[4:a]" in joined
    assert "adelay=250|250" in joined
    assert "volume=-30.0dB" in joined
    assert "amix=inputs=2" in joined
    assert "normalize=0" in joined
    assert "alimiter=limit=0.95" in joined
    assert output == "finalaudio"


def test_sidecar_subtitles_do_not_create_filter() -> None:
    result = _subtitle_filter(
        subtitle_mode="SIDECAR",
        subtitle_path=Path("episode.srt"),
    )

    assert result is None


def test_burned_subtitles_require_path() -> None:
    with pytest.raises(
        ValueError,
        match="BURNED_SUBTITLE_PATH_REQUIRED",
    ):
        _subtitle_filter(
            subtitle_mode="BURNED_IN",
            subtitle_path=None,
        )


def test_burned_subtitles_create_ffmpeg_filter() -> None:
    result = _subtitle_filter(
        subtitle_mode="BURNED_IN",
        subtitle_path=Path(
            r"C:\SIRAJ\Workspace\first-project\episode.srt"
        ),
    )

    assert result is not None
    assert result.startswith("subtitles=")
    assert "charenc=UTF-8" in result