from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from src.application.local_video_production import (
    build_documentary_v2_render,
    build_documentary_v2_storyboard,
    build_documentary_v2_subtitles,
    initialize_documentary_v2,
    verify_documentary_v2_render,
)
from src.application.project_runtime import initialize_project


def _binary(name: str) -> str | None:
    return os.environ.get(f"SIRAJ_{name.upper()}_BINARY") or shutil.which(name)


@pytest.mark.integration
def test_documentary_v2_renders_audible_non_uniform_mp4(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    powershell = shutil.which("powershell.exe")
    if not ffmpeg or not ffprobe or not powershell:
        pytest.skip("Windows local TTS and FFmpeg are required for documentary v2")

    root = tmp_path / "documentary-v2"
    initialize_project(str(root), "documentary-v2", "History of Baghdad", language="en")
    claims = {
        "schema_version": "siraj-knowledge-evidence-v1",
        "claims": [
            {"claim_id": f"claim-{index:02d}", "claim_text": f"Baghdad historical fact {index}.", "evidence_ids": [f"evidence-{index:02d}"]}
            for index in range(6)
        ],
    }
    claim_path = root / "working" / "knowledge" / "claims.json"
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.write_text(json.dumps(claims), encoding="utf-8")

    initialized = initialize_documentary_v2(str(root), powershell=powershell)
    build_documentary_v2_storyboard(str(root), ffmpeg=ffmpeg)
    subtitles = build_documentary_v2_subtitles(str(root))
    rendered = build_documentary_v2_render(str(root), ffmpeg=ffmpeg)
    verified = verify_documentary_v2_render(str(root), ffmpeg=ffmpeg, ffprobe=ffprobe)

    video = root / rendered["video"]
    assert initialized["scene_count"] == 7
    assert 30_000 <= initialized["duration_ms"] <= 60_000
    assert (root / subtitles["subtitles"]).is_file()
    assert video.is_file() and video.stat().st_size > 0
    assert verified["status"] == "VALID"
    assert all(verified["checks"].values())

    frame = subprocess.run(
        [ffmpeg, "-v", "error", "-ss", "3", "-i", str(video), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True,
        capture_output=True,
    ).stdout
    assert len(set(frame)) > 20
