from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.application.montage_pixel_format_recovery_v1 as recovery
import src.application.structural_montage_final_render_v1 as montage
from src.application.structural_montage_final_render_v1 import MontageEnvironment


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _environment(tmp_path: Path) -> MontageEnvironment:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"x")
    ffprobe.write_bytes(b"x")
    return MontageEnvironment(
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        ffmpeg_version_line="ffmpeg test",
        available_filters=montage.REQUIRED_VIDEO_FILTERS,
        missing_filters=(),
    )


def test_render_commands_force_8bit_limited_bt709(tmp_path: Path) -> None:
    command = montage.build_still_render_command(
        _environment(tmp_path),
        tmp_path / "source.jpg",
        tmp_path / "output.mp4",
        duration=2.0,
        motion_profile="SLOW_PUSH_IN",
        fade_in=False,
        fade_out=False,
    )
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert command[command.index("-profile:v") + 1] == "high"
    assert command[command.index("-level:v") + 1] == "4.1"
    assert command[command.index("-color_range") + 1] == "tv"
    assert command[command.index("-colorspace") + 1] == "bt709"
    graph = command[command.index("-filter_complex") + 1]
    assert "out_range=tv" in graph
    assert "format=yuv420p" in graph


def test_non_yuv420p_render_is_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _environment(tmp_path)
    source = tmp_path / "SH-001.rendering.mp4"
    source.write_bytes(b"bad-format")
    formats = iter(("yuv420p10le", "yuv420p"))
    monkeypatch.setattr(montage, "_video_pixel_format", lambda env, path: next(formats))

    def fake_command(command):
        Path(command[-1]).write_bytes(b"normalized")
        return None

    monkeypatch.setattr(montage, "_command", fake_command)
    monkeypatch.setattr(
        montage,
        "_validate_video_file",
        lambda *args, **kwargs: {
            "pixel_format": "yuv420p",
            "duration_seconds": 2.0,
        },
    )
    result = montage._normalize_video_pixel_format_if_needed(
        environment,
        source,
        2.0,
    )
    assert result["applied"] is True
    assert result["input_pixel_format"] == "yuv420p10le"
    assert result["output_pixel_format"] == "yuv420p"
    assert source.read_bytes() == b"normalized"


def test_recovery_archives_only_invalid_temporary_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    episode_id = "episode-001-adam"
    state_path = repo / "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
    episode = repo / "projects" / episode_id
    shot_root = episode / "cinematic/final-render/shots"
    receipt_root = episode / "cinematic/final-render/shot-receipts"
    invalid = shot_root / "SH-001.rendering.mp4"
    complete = shot_root / "SH-002.mp4"
    receipt = receipt_root / "SH-002-receipt.json"
    _write(
        state_path,
        {
            "current_episode_id": episode_id,
            "status": "STRUCTURAL_MONTAGE_FAILED",
            "stage": "STRUCTURAL_MONTAGE",
        },
    )
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_bytes(b"invalid")
    complete.write_bytes(b"complete")
    _write(receipt, {"status": "COMPLETE"})
    environment = _environment(tmp_path)
    monkeypatch.setattr(recovery, "inspect_montage_environment", lambda repo: environment)
    monkeypatch.setattr(recovery, "_video_pixel_format", lambda env, path: "yuv420p10le")
    result = recovery.recover_montage_pixel_format_failure(repo)
    assert result.rendering_files_archived == 1
    assert result.completed_shot_outputs_preserved == 1
    assert result.completed_shot_receipts_preserved == 1
    assert result.paid_media_items_reset == 0
    assert result.provider_requests == 0
    assert not invalid.exists()
    assert complete.read_bytes() == b"complete"
    assert receipt.is_file()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "STRUCTURAL_MONTAGE_FAILED"
    assert state["stage"] == "STRUCTURAL_MONTAGE"
