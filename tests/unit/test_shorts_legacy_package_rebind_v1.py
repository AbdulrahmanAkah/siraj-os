
from pathlib import Path

import pytest

import src.application.shorts_legacy_timing_resolver_v1 as r


def _candidate(
    path: Path,
    *,
    text: str = "نص",
    start: float = 0.0,
) -> r.TimingCandidate:
    segment = r.CanonicalTimedSegment(
        "S1",
        start,
        start + 2.0,
        text,
    )
    return r.TimingCandidate(
        authority_level=3,
        authority_name="LEVEL_3_ABSOLUTE_TTS_TIMELINE_REPAIR",
        source_type="LEGACY_ABSOLUTE_TTS_TIMELINE",
        timing_source_path=path,
        timing_source_sha256="a" * 64,
        segments=(segment,),
        source_audio_path=Path("audio.m4a"),
        source_audio_sha256="b" * 64,
        script_source_path=None,
        script_source_sha256=None,
        duration_seconds=2.0,
        timebase="FINAL_VIDEO_ABSOLUTE",
        offset_seconds=0.0,
        evidence_paths=(),
        audio_binding={"status": "PASS"},
        canonical_explicit=False,
        binding_reason="PACKAGE_AND_AUDIO_FINGERPRINT_EDGE",
    )


def test_same_semantic_timing_wrappers_are_not_false_ambiguity() -> None:
    selected = r._select_candidate(
        (
            _candidate(Path("a/tts-absolute-timeline-repair-v1.json")),
            _candidate(Path("b/tts-absolute-timeline-repair-v1.json")),
        )
    )
    assert selected.segments[0].text == "نص"


def test_material_same_level_timing_conflict_remains_fail_closed() -> None:
    with pytest.raises(r.LegacyTimingResolverError):
        r._select_candidate(
            (
                _candidate(Path("a.json"), text="أ"),
                _candidate(Path("b.json"), text="ب"),
            )
        )


def test_episode_root_follows_external_local_media_package(
    tmp_path: Path,
) -> None:
    code_repo = tmp_path / "code"
    code_repo.mkdir()
    episode = tmp_path / "media" / "episode"
    (episode / "contracts").mkdir(parents=True)
    (episode / "script").mkdir()
    (episode / "evidence").mkdir()
    (episode / "deliverables").mkdir()
    (episode / "orchestration").mkdir()
    (episode / "contracts" / "episode-definition-v1.json").write_text(
        "{}",
        encoding="utf-8",
    )
    video = episode / "deliverables" / "youtube-final-v2" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"x")

    assert r._find_episode_root(video, code_repo) == episode
