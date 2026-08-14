from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import src.application.shorts_legacy_timing_resolver_v1 as resolver
from src.application.shorts_legacy_timing_resolver_v1 import (
    CANONICAL_SCHEMA_VERSION,
    LegacyTimingResolverError,
    resolve_legacy_timing,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _segments(*, text_prefix: str = "نص", offset: float = 0.0) -> list[dict[str, object]]:
    return [
        {
            "segment_id": "S1",
            "start_seconds": offset,
            "end_seconds": offset + 1.0,
            "text": f"{text_prefix} الأول",
        },
        {
            "segment_id": "S2",
            "start_seconds": offset + 1.0,
            "end_seconds": offset + 2.0,
            "text": f"{text_prefix} الثاني",
        },
    ]


def _fixture(
    tmp_path: Path,
    timing: object,
    *,
    timing_name: str = "timing.json",
    duration: float = 4.0,
    manifest_overrides: dict[str, object] | None = None,
    filter_text: str | None = None,
) -> tuple[Path, Path, Path, Path, Path]:
    video = tmp_path / "episode with spaces.mp4"
    audio = tmp_path / "final narration.m4a"
    script = tmp_path / "performance script.json"
    timing_path = tmp_path / timing_name
    video.write_bytes(b"offline video fixture")
    audio.write_bytes(b"offline audio fixture")
    script.write_text(json.dumps({"script": "النص الأصلي"}, ensure_ascii=False), encoding="utf-8")
    if timing_path.suffix.casefold() in {".srt", ".vtt"}:
        timing_path.write_text(str(timing), encoding="utf-8")
    else:
        timing_path.write_text(json.dumps(timing, ensure_ascii=False), encoding="utf-8")
    if filter_text is not None:
        (tmp_path / "timing.filter.txt").write_text(filter_text, encoding="utf-8")
    manifest: dict[str, object] = {
        "episode_id": "TEST-LEGACY-001",
        "episode_display_name": "حلقة اختبار التوقيت",
        "source_video_path": str(video),
        "source_video_sha256": _sha256(video),
        "source_audio_path": str(audio),
        "source_audio_sha256": _sha256(audio),
        "timing_source_path": str(timing_path),
        "timing_source_sha256": _sha256(timing_path),
        "script_path": str(script),
        "script_sha256": _sha256(script),
        "duration_seconds": duration,
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    (tmp_path / "episode-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return video, audio, script, timing_path, tmp_path / "episode-manifest.json"


def _resolve(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    video: Path,
    *,
    persist: bool = False,
):
    monkeypatch.setattr(resolver, "_audio_fingerprint", lambda _path: "f" * 64)
    return resolve_legacy_timing(root, video, persist=persist)


def test_canonical_srt_is_the_highest_priority_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, srt, _manifest = _fixture(
        tmp_path,
        "1\n00:00:00,000 --> 00:00:01,000\nالنص الأول\n\n2\n00:00:01,000 --> 00:00:02,000\nالنص الثاني\n",
        timing_name="canonical.srt",
    )
    legacy = tmp_path / "absolute-timeline.json"
    legacy.write_text(
        json.dumps(
            [
                {"block_id": "L1", "canonical_text_ar": "قديم", "start_seconds": 0, "end_seconds": 1},
                {"block_id": "L2", "canonical_text_ar": "قديم", "start_seconds": 1, "end_seconds": 2},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "legacy.filter.txt").write_text(
        "adelay=0|0\nadelay=1000|1000\natrim=0:4.000000", encoding="utf-8"
    )
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.candidate.timing_source_path == srt.resolve()
    assert result.candidate.authority_level == 1
    assert result.segments[0].text == "النص الأول"


def test_canonical_vtt_is_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, vtt, _manifest = _fixture(
        tmp_path,
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nالنص الأول\n\n00:00:01.000 --> 00:00:02.000\nالنص الثاني\n",
        timing_name="canonical.vtt",
    )
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.candidate.timing_source_path == vtt.resolve()
    assert result.candidate.source_type == "CANONICAL_VTT"


def test_canonical_timed_json_is_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "timebase": "FINAL_VIDEO",
        "segments": _segments(),
    }
    video, _audio, _script, timing, _manifest = _fixture(
        tmp_path, payload, timing_name="canonical-timed-transcript.json"
    )
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.candidate.timing_source_path == timing.resolve()
    assert result.candidate.authority_level == 1


def test_native_narration_timing_map_is_recovered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "timebase": "FINAL_VIDEO",
        "narration_timing_map": {"segments": _segments()},
    }
    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path, payload, timing_name="narration-timing-map.json"
    )
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.candidate.authority_level == 2
    assert result.candidate.source_type == "NATIVE_NARRATION_TIMING_MAP"


def test_absolute_legacy_timeline_uses_filter_proof_for_final_video_timebase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = [
        {"block_id": "B1", "canonical_text_ar": "النص الأول", "start_seconds": 0, "end_seconds": 1},
        {"block_id": "B2", "canonical_text_ar": "النص الثاني", "start_seconds": 1.25, "end_seconds": 2.25},
    ]
    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path,
        payload,
        timing_name="tts-absolute-timeline.json",
        filter_text="adelay=0|0\nadelay=1250|1250\natrim=0:4.000000",
    )
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.candidate.source_type == "LEGACY_ABSOLUTE_TTS_TIMELINE"
    assert result.candidate.timebase == "FINAL_VIDEO_ABSOLUTE"
    assert result.candidate.offset_seconds == 0.0
    assert result.segments[-1].end_seconds == 2.25


def test_hash_binding_ignores_unrelated_output_hash_in_same_evidence_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = [
        {"block_id": "B1", "canonical_text_ar": "النص الأول", "start_seconds": 0, "end_seconds": 1},
        {"block_id": "B2", "canonical_text_ar": "النص الثاني", "start_seconds": 1, "end_seconds": 2},
    ]
    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path,
        payload,
        timing_name="tts-absolute-timeline.json",
        filter_text="adelay=0|0\nadelay=1000|1000\natrim=0:4.000000",
    )
    unrelated = tmp_path / "editorial-rescue-output.mp4"
    unrelated.write_bytes(b"unrelated output")
    (tmp_path / "editorial-rescue-summary.json").write_text(
        json.dumps(
            {
                "source_master": str(video),
                "source_master_sha256": _sha256(video),
                "output_master": str(unrelated),
                "output_master_sha256": _sha256(unrelated),
            }
        ),
        encoding="utf-8",
    )
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.canonical_document["source_video_sha256"] == _sha256(video)


def test_episode_identity_script_binding_requires_declared_canonical_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = [
        {"block_id": "B1", "canonical_text_ar": "النص الأول", "start_seconds": 0, "end_seconds": 1},
        {"block_id": "B2", "canonical_text_ar": "النص الثاني", "start_seconds": 1, "end_seconds": 2},
    ]
    video, _audio, script, _timing, manifest = _fixture(
        tmp_path,
        payload,
        timing_name="tts-absolute-timeline.json",
        filter_text="adelay=0|0\nadelay=1000|1000\natrim=0:4.000000",
    )
    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_value.pop("script_path", None)
    manifest_value.pop("script_sha256", None)
    manifest.write_text(json.dumps(manifest_value, ensure_ascii=False), encoding="utf-8")
    canonical_script_hash = hashlib.sha256(
        json.dumps(
            json.loads(script.read_text(encoding="utf-8")),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    (tmp_path / "final-script-approval.json").write_text(
        json.dumps(
            {
                "episode_id": "TEST-LEGACY-001",
                "script_path_relative": script.name,
                "script_canonical_sha256": canonical_script_hash,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.candidate.script_source_path == script.resolve()
    assert result.candidate.script_source_sha256 == _sha256(script)


def test_narration_relative_offset_is_applied_only_when_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "timebase": "NARRATION_RELATIVE",
        "offset_seconds": 1.25,
        "segments": _segments(),
    }
    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path, payload, timing_name="sentence-timing.json", duration=5.0
    )
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.candidate.timebase == "FINAL_VIDEO_OFFSET_APPLIED"
    assert result.candidate.offset_seconds == 1.25
    assert result.segments[0].start_seconds == 1.25


def test_stale_video_hash_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    video.write_bytes(b"changed video")
    with pytest.raises(LegacyTimingResolverError, match="TIMING_SOURCE_STALE:VIDEO_HASH_MISMATCH"):
        _resolve(monkeypatch, tmp_path, video)


def test_stale_audio_hash_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, audio, _script, _timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    audio.write_bytes(b"changed audio")
    with pytest.raises(LegacyTimingResolverError, match="TIMING_SOURCE_STALE:AUDIO_HASH_MISMATCH"):
        _resolve(monkeypatch, tmp_path, video)


def test_stale_timing_hash_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    timing.write_text(
        json.dumps({"timebase": "FINAL_VIDEO", "segments": _segments(text_prefix="تغير")}, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(LegacyTimingResolverError, match="TIMING_SOURCE_STALE:TIMING_HASH_MISMATCH"):
        _resolve(monkeypatch, tmp_path, video)


def test_stale_script_hash_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, script, _timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    script.write_text(json.dumps({"script": "نسخة مختلفة"}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LegacyTimingResolverError, match="TIMING_SOURCE_STALE:SCRIPT_HASH_MISMATCH"):
        _resolve(monkeypatch, tmp_path, video)


def test_equal_priority_sources_are_ambiguous(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, first, _manifest = _fixture(
        tmp_path,
        "1\n00:00:00,000 --> 00:00:01,000\nالأول\n\n2\n00:00:01,000 --> 00:00:02,000\nالثاني\n",
        timing_name="first.srt",
    )
    second = tmp_path / "second.vtt"
    second.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nالأول\n\n00:00:01.000 --> 00:00:02.000\nالثاني\n",
        encoding="utf-8",
    )
    assert first.is_file() and second.is_file()
    with pytest.raises(LegacyTimingResolverError, match="TIMING_SOURCE_AMBIGUOUS"):
        _resolve(monkeypatch, tmp_path, video)


def test_missing_timing_requires_user_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, timing, manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    timing.unlink()
    manifest.unlink()
    with pytest.raises(LegacyTimingResolverError, match="TIMING_EVIDENCE_INSUFFICIENT"):
        _resolve(monkeypatch, tmp_path, video)


def test_malformed_timing_json_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}, timing_name="malformed-timing.json"
    )
    timing.write_text("{malformed", encoding="utf-8")
    with pytest.raises(LegacyTimingResolverError, match="TIMING_EVIDENCE_INSUFFICIENT"):
        _resolve(monkeypatch, tmp_path, video)


@pytest.mark.parametrize(
    ("segments", "detail"),
    [
        (
            [
                {"segment_id": "S1", "start_seconds": 0, "end_seconds": 2, "text": "الأول"},
                {"segment_id": "S2", "start_seconds": 1, "end_seconds": 3, "text": "الثاني"},
            ],
            "SEGMENTS_OVERLAP",
        ),
        (
            [{"segment_id": "S1", "start_seconds": 0, "end_seconds": 5, "text": "يتجاوز"}],
            "SEGMENT_BEYOND_DURATION",
        ),
    ],
)
def test_invalid_segment_ranges_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    segments: list[dict[str, object]],
    detail: str,
) -> None:
    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": segments}
    )
    with pytest.raises(LegacyTimingResolverError, match=detail):
        _resolve(monkeypatch, tmp_path, video)


def test_arabic_text_is_preserved_exactly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exact = "مَرْحَبًا، يا آدم — نصٌّ أصيلٌ بلا تعديل"
    payload = {
        "timebase": "FINAL_VIDEO",
        "segments": [{"segment_id": "S1", "start_seconds": 0, "end_seconds": 1, "text": exact}],
    }
    video, _audio, _script, _timing, _manifest = _fixture(tmp_path, payload, duration=2.0)
    result = _resolve(monkeypatch, tmp_path, video)
    assert result.segments[0].text == exact


def test_unicode_and_space_paths_are_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "مجلد حلقة قديمة"
    root.mkdir()
    video, _audio, _script, _timing, _manifest = _fixture(
        root, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    result = _resolve(monkeypatch, root, video)
    assert result.episode_id == "TEST-LEGACY-001"
    assert result.candidate.timing_source_path.parent == root.resolve()


def test_cache_is_reused_when_all_hashes_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    first = _resolve(monkeypatch, tmp_path, video, persist=True)
    second = _resolve(monkeypatch, tmp_path, video, persist=True)
    assert first.status == "AUTO_DISCOVERED"
    assert second.status == "CACHE_REUSED"
    assert second.canonical_transcript_sha256 == first.canonical_transcript_sha256


def test_cache_invalidates_when_resolver_version_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    first = _resolve(monkeypatch, tmp_path, video, persist=True)
    monkeypatch.setattr(resolver, "RESOLVER_VERSION", "1.0.1")
    second = _resolve(monkeypatch, tmp_path, video, persist=True)
    assert first.cache_key != second.cache_key
    assert second.status == "AUTO_DISCOVERED"


def test_engine_source_admission_uses_resolved_legacy_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.application.shorts_derivative_engine_v1 as engine_module
    from src.application.shorts_derivative_engine_v1 import ShortsDerivativeEngine

    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path, {"timebase": "FINAL_VIDEO", "segments": _segments()}
    )
    monkeypatch.setattr(resolver, "_audio_fingerprint", lambda _path: "f" * 64)
    real_resolver = engine_module.resolve_legacy_timing

    def no_persist(*args: object, **kwargs: object):
        kwargs["persist"] = False
        return real_resolver(*args, **kwargs)

    monkeypatch.setattr(engine_module, "resolve_legacy_timing", no_persist)
    monkeypatch.setattr(
        engine_module,
        "_probe_with_ffmpeg",
        lambda _path, **_kwargs: {"available": False, "duration_seconds": None, "has_audio": None},
    )
    real_engine_sha256 = engine_module._sha256_file
    monkeypatch.setattr(
        engine_module,
        "_sha256_file",
        lambda path: real_engine_sha256(path) if Path(path).is_file() else "e" * 64,
    )
    episode = ShortsDerivativeEngine(Path(__file__).resolve().parents[2]).ingest(
        mode="VIDEO_PLUS_TRANSCRIPT", video_path=video
    )
    assert episode.source_admission["status"] == "PASS"
    assert episode.source_admission["transcript_bound"] is True
    assert episode.legacy_source is True
    assert len(episode.narration_segments) == 2


def test_source_discovery_marks_legacy_timing_ready_without_manual_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.application.shorts_source_discovery_v1 import discover_episode_sources

    video, _audio, _script, _timing, _manifest = _fixture(
        tmp_path,
        [
            {"block_id": "B1", "canonical_text_ar": "النص الأول", "start_seconds": 0, "end_seconds": 1},
            {"block_id": "B2", "canonical_text_ar": "النص الثاني", "start_seconds": 1, "end_seconds": 2},
        ],
        timing_name="tts-absolute-timeline.json",
        filter_text="adelay=0|0\nadelay=1000|1000\natrim=0:4.000000",
    )
    monkeypatch.setattr(resolver, "_audio_fingerprint", lambda _path: "f" * 64)
    discovery = discover_episode_sources(video, repo_root=tmp_path)
    assert discovery.status == "READY"
    assert discovery.ready_without_manual_file is True
    assert discovery.legacy_timing_resolution is not None
    assert discovery.legacy_timing_resolution.episode_id == "TEST-LEGACY-001"


def test_desktop_resume_invalidates_when_timing_evidence_hash_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.application.shorts_derivative_desktop_integration_v1 import (
        ShortsDerivativeDesktopWorkflow,
    )

    import src.application.shorts_derivative_engine_v1 as engine_module

    video = tmp_path / "resume-video.mp4"
    metadata = tmp_path / "metadata.json"
    transcript = tmp_path / "resume.srt"
    video.write_bytes(b"offline video")
    metadata.write_text(
        json.dumps(
            {
                "episode_id": "RESUME-LEGACY-001",
                "episode_display_name": "استئناف اختبار",
                "duration_seconds": 2,
                "constitution_version": "1.0.0",
                "claims": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nالأول\n\n2\n00:00:01,000 --> 00:00:02,000\nالثاني\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        engine_module,
        "_probe_with_ffmpeg",
        lambda _path, **_kwargs: {"available": False, "duration_seconds": None, "has_audio": None},
    )
    desktop = tmp_path / "Desktop"
    settings = tmp_path / "settings.json"
    workflow = ShortsDerivativeDesktopWorkflow(
        Path(__file__).resolve().parents[2],
        desktop_location=desktop,
        settings_path=settings,
    )
    workflow.select_episode(
        mode="VIDEO_PLUS_TRANSCRIPT",
        video_path=video,
        metadata_path=metadata,
        transcript_path=transcript,
    )
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nتغير الدليل\n\n2\n00:00:01,000 --> 00:00:02,000\nالثاني\n",
        encoding="utf-8",
    )
    resumed = ShortsDerivativeDesktopWorkflow(
        Path(__file__).resolve().parents[2],
        desktop_location=desktop,
        settings_path=settings,
    )
    resumed.select_episode(
        mode="VIDEO_PLUS_TRANSCRIPT",
        video_path=video,
        metadata_path=metadata,
        transcript_path=transcript,
    )
    assert resumed.resume_status == "STALE_SOURCE_EVIDENCE"
