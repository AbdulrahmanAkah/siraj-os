from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from src.application.local_video_production import (
    build_render,
    build_storyboard,
    build_subtitles,
    initialize_production,
    verify_render,
)
from src.application.project_runtime import initialize_project


def _binary(name: str) -> str | None:
    return os.environ.get(f"SIRAJ_{name.upper()}_BINARY") or shutil.which(name)


@pytest.mark.integration
def test_local_production_slice_renders_valid_mp4(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg and ffprobe are required for local render integration")

    project_root = tmp_path / "project"
    initialize_project(
        str(project_root),
        "video-slice",
        "History of Baghdad",
        language="en",
    )
    claims = {
        "schema_version": "siraj-knowledge-evidence-v1",
        "claims": [
            {
                "claim_id": f"claim-{index:02d}",
                "claim_text": f"Baghdad historical fact {index}.",
                "evidence_ids": [f"evidence-{index:02d}"],
            }
            for index in range(6)
        ],
    }
    claim_path = project_root / "working" / "knowledge" / "claims.json"
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.write_text(json.dumps(claims), encoding="utf-8")

    initialized = initialize_production(str(project_root))
    storyboard = build_storyboard(str(project_root), ffmpeg=ffmpeg)
    subtitles = build_subtitles(str(project_root))
    rendered = build_render(str(project_root), ffmpeg=ffmpeg)
    verified = verify_render(str(project_root), ffprobe=ffprobe)

    assert initialized["scene_count"] == 6
    assert storyboard["asset_count"] == 6
    assert subtitles["cue_count"] == 6
    assert (project_root / rendered["video"]).is_file()
    assert (project_root / rendered["video"]).stat().st_size > 0
    assert verified["status"] == "VALID"
    assert all(verified["checks"].values())
