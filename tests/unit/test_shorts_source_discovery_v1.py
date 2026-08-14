from __future__ import annotations

import json
from pathlib import Path

from src.application.shorts_source_discovery_v1 import discover_episode_sources


def _video(path: Path) -> None:
    path.write_bytes(b"local-video-fixture")


def _metadata(path: Path, episode_id: str, *, timing: bool = True) -> None:
    payload = {"episode_id": episode_id, "episode_display_name": "حلقة اختبار", "claims": []}
    if timing:
        payload["segments"] = [{"id": "S1", "start": 0, "end": 2, "text": "نص"}]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_video_with_one_timed_metadata_is_auto_ready(tmp_path: Path) -> None:
    video = tmp_path / "حلقة اختبار.mp4"
    _video(video)
    _metadata(tmp_path / "metadata.json", "EP-001")

    result = discover_episode_sources(video)

    assert result.status == "READY"
    assert result.matched_metadata is not None
    assert result.matched_metadata.path.name == "metadata.json"
    assert result.matched_transcript is None


def test_metadata_without_timing_binds_one_local_transcript(tmp_path: Path) -> None:
    video = tmp_path / "episode.mov"
    _video(video)
    _metadata(tmp_path / "episode_metadata.json", "EP-002", timing=False)
    (tmp_path / "episode.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:02.000\nنص\n", encoding="utf-8")

    result = discover_episode_sources(video)

    assert result.matched_metadata is not None
    assert result.matched_transcript is not None
    assert result.matched_transcript.path.suffix == ".vtt"


def test_multiple_metadata_candidates_stop_for_human_choice(tmp_path: Path) -> None:
    video = tmp_path / "episode.mkv"
    _video(video)
    _metadata(tmp_path / "metadata-a.json", "EP-A")
    _metadata(tmp_path / "metadata-b.json", "EP-B")

    result = discover_episode_sources(video)

    assert result.status == "AMBIGUOUS"
    assert result.metadata_ambiguous is True
    assert result.matched_metadata is None
    assert {item.episode_id for item in result.metadata_candidates} == {"EP-A", "EP-B"}


def test_unrelated_nearby_metadata_is_never_silently_selected(tmp_path: Path) -> None:
    video = tmp_path / "chosen-video.webm"
    _video(video)
    _metadata(tmp_path / "unrelated.json", "OTHER-EPISODE")
    _metadata(tmp_path / "second-unrelated.json", "OTHER-EPISODE-2")

    result = discover_episode_sources(video)

    assert result.matched_metadata is None
    assert result.status == "AMBIGUOUS"


def test_stale_metadata_hash_is_blocked_before_ingestion(tmp_path: Path) -> None:
    video = tmp_path / "episode.avi"
    _video(video)
    payload = {"episode_id": "EP-STALE", "source_episode_sha256": "0" * 64, "segments": [{"start": 0, "end": 1, "text": "نص"}]}
    (tmp_path / "metadata.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = discover_episode_sources(video)

    assert result.status == "STALE_SOURCE"
    assert result.matched_metadata is None
    assert result.metadata_candidates[0].source_hash_match is False


def test_invalid_metadata_is_not_treated_as_a_source(tmp_path: Path) -> None:
    video = tmp_path / "episode.m4v"
    _video(video)
    (tmp_path / "metadata.json").write_text("not-json", encoding="utf-8")

    result = discover_episode_sources(video)

    assert result.status == "METADATA_REQUIRED"
    assert result.metadata_candidates == ()
