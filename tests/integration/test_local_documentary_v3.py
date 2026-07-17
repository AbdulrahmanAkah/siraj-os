from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from src.application.local_video_production import (
    DocumentaryV3Config,
    build_documentary_v3_assets,
    build_documentary_v3_render,
    build_documentary_v3_subtitles,
    initialize_documentary_v3,
    verify_documentary_v3_render,
)
from src.application.project_runtime import initialize_project


def _binary(name: str) -> str | None:
    return os.environ.get(f"SIRAJ_{name.upper()}_BINARY") or shutil.which(name)


@pytest.mark.integration
def test_arabic_documentary_v3_is_audible_licensed_and_music_free(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    espeak = shutil.which("espeak-ng") or (r"C:\Program Files\eSpeak NG\espeak-ng.exe" if Path(r"C:\Program Files\eSpeak NG\espeak-ng.exe").is_file() else None)
    if not ffmpeg or not ffprobe or not espeak:
        pytest.skip("local FFmpeg, ffprobe, and eSpeak NG Arabic are required")

    root = tmp_path / "arabic-v3"
    initialize_project(str(root), "arabic-v3", "History of Baghdad", language="ar")
    claims = {"schema_version": "siraj-knowledge-evidence-v1", "claims": [
        {"claim_id": "claim-1", "claim_text": "Baghdad was founded in the year 762.", "evidence_ids": ["evidence_dfb4a0f18c04c2b7"]},
        {"claim_id": "claim-2", "claim_text": "The Abbasid caliph Al-Mansur founded Baghdad.", "evidence_ids": ["evidence_b4c3cf491ba6b04e"]},
        {"claim_id": "claim-3", "claim_text": "The Tigris River flows through Baghdad.", "evidence_ids": ["evidence_acd598236f328438"]},
        {"claim_id": "claim-4", "claim_text": "Baghdad became a major center of learning.", "evidence_ids": ["evidence_571e76d39ea10eb1"]},
        {"claim_id": "claim-5", "claim_text": "The House of Wisdom operated in Baghdad.", "evidence_ids": ["evidence_e9d47df93efc4d5c"]},
        {"claim_id": "claim-6", "claim_text": "Baghdad is the capital of Iraq.", "evidence_ids": ["evidence_431f1c60aff4b558"]},
    ]}
    path = root / "working" / "knowledge" / "claims.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(claims), encoding="utf-8")
    config = DocumentaryV3Config(ffmpeg=ffmpeg, ffprobe=ffprobe)

    initialize_documentary_v3(str(root), config=config)
    build_documentary_v3_assets(str(root), config=config)
    subtitles = build_documentary_v3_subtitles(str(root))
    rendered = build_documentary_v3_render(str(root), config=config)
    verified = verify_documentary_v3_render(str(root), config=config)

    script = json.loads((root / "working" / "production-v3" / "script-v3.json").read_text(encoding="utf-8"))
    narration = " ".join(scene["narration_tts"] for scene in script["scenes"])
    assert any("\u0621" <= char <= "\u064a" for char in narration)
    assert not any(token in narration.lower() for token in ("historical fact number", "this fact is documented", "claim id", "source id"))
    assert all("screen_title" in scene and "editorial_note" in scene and "citation_ids" in scene for scene in script["scenes"])
    assert 60_000 <= sum(scene["duration_ms"] for scene in script["scenes"]) <= 90_000
    assert (root / subtitles["srt"]).is_file() and (root / subtitles["vtt"]).is_file()
    srt_text = (root / subtitles["srt"]).read_text(encoding="utf-8").replace("\u200f", "")
    vtt_text = (root / subtitles["vtt"]).read_text(encoding="utf-8").replace("\u200f", "")
    assert all(scene["narration_ar"] in srt_text and scene["narration_ar"] in vtt_text for scene in script["scenes"])
    assert verified["status"] == "VALID" and all(verified["checks"].values())

    video = root / rendered["video"]
    raw = subprocess.run([ffmpeg, "-v", "error", "-ss", "6", "-i", str(video), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    assert len(set(raw)) > 20
