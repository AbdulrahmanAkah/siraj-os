from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.local_video_production.render_adapter_v1 import (
    RENDER_ADAPTER_SCHEMA_VERSION,
    LocalVideoRenderAdapter,
    _validate_manifest,
)


def valid_manifest() -> dict:
    return {
        "schema_version": (
            RENDER_ADAPTER_SCHEMA_VERSION
        ),
        "render_id": "test-render",
        "video": {
            "width": 1920,
            "height": 1080,
            "fps": 24,
            "transition_ms": 450,
        },
        "audio": {
            "path": "audio.wav",
        },
        "assets": [
            {
                "path": "one.png",
                "motion": "PUSH_IN",
            },
            {
                "path": "two.png",
                "motion": (
                    "PAN_LEFT_TO_RIGHT"
                ),
            },
        ],
        "output": {
            "video": "exports/test.mp4",
            "report": (
                "manifests/test-report.json"
            ),
        },
    }


def test_render_manifest_contract_accepts_valid_data() -> None:
    _validate_manifest(
        valid_manifest()
    )


def test_render_manifest_rejects_unknown_motion() -> None:
    manifest = valid_manifest()

    manifest["assets"][0][
        "motion"
    ] = "UNSUPPORTED"

    with pytest.raises(
        ValueError,
        match="VIDEO_ASSET_MOTION_INVALID",
    ):
        _validate_manifest(manifest)


def test_render_manifest_rejects_missing_audio() -> None:
    manifest = valid_manifest()
    manifest["audio"] = {}

    with pytest.raises(
        ValueError,
        match="FINAL_AUDIO_REQUIRED",
    ):
        _validate_manifest(manifest)


def test_adapter_rejects_missing_project_root(
    tmp_path: Path,
) -> None:
    adapter = object.__new__(
        LocalVideoRenderAdapter
    )

    adapter.ffmpeg = "ffmpeg"
    adapter.ffprobe = "ffprobe"

    with pytest.raises(
        FileNotFoundError,
        match="PROJECT_ROOT_NOT_FOUND",
    ):
        adapter.render(
            tmp_path / "missing",
            tmp_path / "manifest.json",
        )


def test_replay_manifest_is_manifest_driven() -> None:
    path = Path(
        r"C:\SIRAJ\Workspace\first-project"
        r"\manifests"
        r"\render-adapter-v1-replay.json"
    )

    assert path.is_file()

    manifest = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert (
        manifest["schema_version"]
        == RENDER_ADAPTER_SCHEMA_VERSION
    )

    assert (
        manifest["output"]["video"]
        == "exports/render-adapter-v1-replay.mp4"
    )

    assert len(manifest["assets"]) == 3
