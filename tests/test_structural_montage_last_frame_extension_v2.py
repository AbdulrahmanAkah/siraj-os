
from pathlib import Path

from src.application.structural_montage_final_render_v1 import (
    MAX_LAST_FRAME_EXTENSION_SECONDS,
    MontageEnvironment,
    build_motion_render_command,
)


def _environment() -> MontageEnvironment:
    return MontageEnvironment(
        ffmpeg_path=Path("ffmpeg"),
        ffprobe_path=Path("ffprobe"),
        ffmpeg_version_line="test",
        available_filters=frozenset(),
        missing_filters=(),
    )


def test_motion_render_caps_last_frame_extension() -> None:
    command = build_motion_render_command(
        _environment(),
        Path("source.mp4"),
        Path("output.mp4"),
        duration=10.0,
        source_duration=2.0,
        fade_in=False,
        fade_out=False,
        graphics=False,
    )
    filter_graph = command[
        command.index("-filter_complex") + 1
    ]
    assert (
        f"stop_duration={MAX_LAST_FRAME_EXTENSION_SECONDS:.6f}"
        in filter_graph
    )
    assert "stop_duration=min(" not in filter_graph


def test_motion_render_uses_only_required_short_extension() -> None:
    command = build_motion_render_command(
        _environment(),
        Path("source.mp4"),
        Path("output.mp4"),
        duration=5.7,
        source_duration=5.0,
        fade_in=False,
        fade_out=False,
        graphics=True,
    )
    filter_graph = command[
        command.index("-filter_complex") + 1
    ]
    assert "stop_duration=0.700000" in filter_graph
