from __future__ import annotations

import json
from pathlib import Path
import wave

import pytest

from src.application.local_video_production.subtitles_v1 import (
    SUBTITLE_TIMING_ESTIMATED,
    SUBTITLE_TIMING_EXACT,
    SubtitleRequest,
    SubtitleStyleConfig,
    SubtitleTimingConfig,
    TranscriptSegment,
    build_subtitle_track,
    generate_subtitles,
    render_subtitle_configuration,
    segment_arabic_text,
    validate_subtitle_track,
    wrap_arabic_lines,
)


def _wav(path: Path, *, duration_ms: int = 6000) -> Path:
    frames = 24 * duration_ms
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * frames)
    return path


def _request(tmp_path: Path, **kwargs: object) -> SubtitleRequest:
    data: dict[str, object] = {
        "mastered_audio_path": _wav(tmp_path / "mastered.wav"),
        "transcript": "في بغداد، ازدهرت مدينة العلم والترجمة. ثم امتد أثرها إلى آفاق واسعة.",
        "output_directory": tmp_path / "subtitles",
    }
    data.update(kwargs)
    return SubtitleRequest(**data)  # type: ignore[arg-type]


def test_arabic_sentence_segmentation_and_punctuation() -> None:
    config = SubtitleTimingConfig()
    cues = segment_arabic_text("في بغداد، ازدهرت العلوم؛ ثم انتقلت المعرفة؟ نعم!", config)
    assert cues == ["في بغداد، ازدهرت العلوم؛", "ثم انتقلت المعرفة؟ نعم!"]


def test_long_sentence_is_split_without_breaking_words() -> None:
    config = SubtitleTimingConfig(maximum_characters_per_line=40, preferred_words_per_cue=8)
    cues = segment_arabic_text("كانت بغداد مدينة واسعة تجمع العلماء والكتب والمترجمين في مجالس علمية متتابعة عبر السنين.", config)
    assert len(cues) > 1
    assert all(not cue.endswith(" من") for cue in cues)


def test_rtl_line_wrap_is_balanced_and_preserves_text() -> None:
    config = SubtitleTimingConfig()
    text = "في قلب بغداد ازدهرت حركة الترجمة والعلوم والفلسفة في زمن قصير"
    lines = wrap_arabic_lines(text, config)
    assert len(lines) == 2
    assert " ".join(lines) == text
    assert all(len(line) <= 40 for line in lines)


def test_estimated_track_aligns_to_mastered_audio_deterministically(tmp_path: Path) -> None:
    request = _request(tmp_path)
    first = build_subtitle_track(request)
    second = build_subtitle_track(request)
    assert first.timing_source == SUBTITLE_TIMING_ESTIMATED
    assert first.cues == second.cues
    assert first.cues[-1].end_ms == first.audio_duration_ms
    assert all(current.start_ms >= previous.end_ms for previous, current in zip(first.cues, first.cues[1:]))


def test_exact_timing_metadata_is_used_and_speaker_turns_are_not_mixed(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        transcript=None,
        transcript_segments=(
            TranscriptSegment("قال الراوي: بدأت القصة.", "narrator", "الراوي", "PRIMARY_NARRATOR", "Alnilam", "scene-1", 0, 2500),
            TranscriptSegment("وأجاب المؤرخ: بقيت آثارها.", "historian", "المؤرخ", "HISTORICAL_CHARACTER", "Charon", "scene-1", 2600, 5200),
        ),
    )
    track = build_subtitle_track(request)
    assert track.timing_source == SUBTITLE_TIMING_EXACT
    assert {cue.speaker_id for cue in track.cues} == {"narrator", "historian"}
    assert all(cue.start_ms >= 0 and cue.end_ms <= track.audio_duration_ms for cue in track.cues)


def test_exports_manifest_validation_and_render_readiness(tmp_path: Path) -> None:
    request = _request(tmp_path, style_config=SubtitleStyleConfig(include_speaker_prefix=True))
    track, result, validation = generate_subtitles(request)
    assert validation.status in {"PASS", "PASS_WITH_WARNINGS"}
    assert result.srt_path.read_text(encoding="utf-8").count(" --> ") == len(track.cues)
    assert result.vtt_path.read_text(encoding="utf-8").startswith("WEBVTT")
    assert "<v" not in result.vtt_path.read_text(encoding="utf-8")
    assert "[V4+ Styles]" in result.ass_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["direction"] == "RTL"
    assert manifest["cue_metadata"][0]["cue_id"] == "cue-001"
    assert render_subtitle_configuration(result) == {"mode": "BURNED_IN", "path": str(result.ass_path)}
    assert render_subtitle_configuration(result, burn_in=False)["path"].endswith(".srt")


def test_cache_hit_and_invalidation(tmp_path: Path) -> None:
    request = _request(tmp_path)
    _, first, _ = generate_subtitles(request)
    _, second, _ = generate_subtitles(request)
    assert first.cache_hit is False
    assert second.cache_hit is True
    changed = _request(tmp_path, transcript="بغداد مدينة العلم.")
    _, third, _ = generate_subtitles(changed)
    assert third.cache_hit is False


def test_invalid_audio_and_empty_transcript_fail_early(tmp_path: Path) -> None:
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not a wav")
    with pytest.raises(ValueError, match="SUBTITLE_MASTERED_AUDIO_INVALID"):
        build_subtitle_track(SubtitleRequest(broken, "نص", output_directory=tmp_path))
    with pytest.raises(ValueError, match="SUBTITLE_TRANSCRIPT_REQUIRED"):
        build_subtitle_track(SubtitleRequest(_wav(tmp_path / "ok.wav"), None, output_directory=tmp_path))


def test_validation_detects_corrupt_export_and_line_limit(tmp_path: Path) -> None:
    request = _request(tmp_path)
    track, result, _ = generate_subtitles(request)
    result.srt_path.write_text("", encoding="utf-8")
    validation = validate_subtitle_track(track, request.timing_config, {"srt": result.srt_path})
    assert validation.status == "FAIL"
    assert "EXPORT_INVALID:srt" in validation.errors


def test_ass_uses_distinct_dialogue_style(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        transcript=None,
        transcript_segments=(TranscriptSegment("قال المؤرخ إن بغداد مدينة عظيمة.", "speaker", "المؤرخ", "DIALOGUE", "Charon", "scene", 0, 5000),),
    )
    _, result, _ = generate_subtitles(request)
    content = result.ass_path.read_text(encoding="utf-8")
    assert "Style: Dialogue" in content
    assert ",Dialogue," in content


def test_vtt_keeps_optional_speaker_metadata(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        transcript=None,
        transcript_segments=(TranscriptSegment("قال المؤرخ إن بغداد مدينة عظيمة.", "speaker", "المؤرخ", "DIALOGUE", "Charon", "scene", 0, 5000),),
    )
    _, result, _ = generate_subtitles(request)
    assert "<v المؤرخ>" in result.vtt_path.read_text(encoding="utf-8")


def test_no_network_or_secret_fields_are_needed(tmp_path: Path) -> None:
    _, result, _ = generate_subtitles(_request(tmp_path))
    manifest = result.manifest_path.read_text(encoding="utf-8")
    assert "API_KEY" not in manifest
    assert "http://" not in manifest and "https://" not in manifest
