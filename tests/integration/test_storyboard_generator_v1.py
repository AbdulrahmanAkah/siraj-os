from __future__ import annotations

import json
from pathlib import Path
import wave

import pytest

from src.application.local_video_production.storyboard_generator_v1 import (
    STORYBOARD_SCHEMA_V1,
    StoryboardConfig,
    StoryboardRequest,
    generate_storyboard,
    render_timeline_from_storyboard,
)
from src.application.local_video_production.subtitles_v1 import (
    SubtitleRequest,
    TranscriptSegment,
    generate_subtitles,
)


def _wav(path: Path, duration_ms: int = 30000) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * (24 * duration_ms))
    return path


def _subtitle_manifest(tmp_path: Path) -> tuple[Path, Path]:
    audio = _wav(tmp_path / "mastered.wav")
    segments = (
        TranscriptSegment("في بغداد، بدأت الحكاية من نهر دجلة ومدينة تجمع المعرفة.", "narrator", "الراوي", "PRIMARY_NARRATOR", "Alnilam", "scene-opening", 0, 5000),
        TranscriptSegment("ثم انتقلت الرسائل إلى خراسان، فتغير مسار الدولة في عام جديد.", "narrator", "الراوي", "PRIMARY_NARRATOR", "Alnilam", "scene-map", 5100, 10000),
        TranscriptSegment("قال المؤرخ: إن الوثيقة تكشف لحظة تولية حاسمة.", "historian", "المؤرخ", "HISTORICAL_CHARACTER", "Charon", "scene-dialogue", 10100, 15000),
        TranscriptSegment("لكن الأزمة اشتدت، وظهر الصراع قبل أن يتبين أثر القرار.", "historian", "المؤرخ", "HISTORICAL_CHARACTER", "Charon", "scene-climax", 15100, 21000),
        TranscriptSegment("وفي الختام، بقيت المخطوطات شاهدة على ما صنعته بغداد.", "narrator", "الراوي", "PRIMARY_NARRATOR", "Alnilam", "scene-ending", 21100, 30000),
    )
    _, result, validation = generate_subtitles(SubtitleRequest(audio, None, segments, tmp_path / "subtitles", tmp_path / "production-subtitles.json"))
    assert validation.status in {"PASS", "PASS_WITH_WARNINGS"}
    return audio, result.manifest_path


def _request(tmp_path: Path, **kwargs: object) -> StoryboardRequest:
    audio, subtitles = _subtitle_manifest(tmp_path)
    values: dict[str, object] = {"mastered_audio_path": audio, "subtitle_manifest_path": subtitles, "output_directory": tmp_path / "storyboard", "manifest_path": tmp_path / "production-storyboard.json"}
    values.update(kwargs)
    return StoryboardRequest(**values)  # type: ignore[arg-type]


def test_storyboard_builds_narrative_arc_scenes_beats_and_shots(tmp_path: Path) -> None:
    scenes, result, validation = generate_storyboard(_request(tmp_path))
    assert validation.status == "PASS"
    assert validation.quality_grade in {"STRONG", "EXCELLENT"}
    assert len(scenes) >= 4
    assert scenes[0].narrative_purpose == "OPENING_HOOK"
    payload = json.loads(result.storyboard_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == STORYBOARD_SCHEMA_V1
    assert len(payload["beats"]) >= 5


def test_scene_boundaries_cover_location_time_and_speaker_turns(tmp_path: Path) -> None:
    scenes, _, _ = generate_storyboard(_request(tmp_path))
    assert len(scenes) >= 4
    assert any(scene.location == "بغداد" for scene in scenes)
    assert any("HISTORICAL_CHARACTER" in {shot.role for shot in scene.shots} for scene in scenes)


def test_shot_timing_has_full_coverage_without_gaps_or_overlap(tmp_path: Path) -> None:
    scenes, _, validation = generate_storyboard(_request(tmp_path))
    shots = [shot for scene in scenes for shot in scene.shots]
    assert shots[0].timing.start_ms == 0
    assert shots[-1].timing.end_ms == 30000
    assert all(right.timing.start_ms == left.timing.end_ms for left, right in zip(shots, shots[1:]))
    assert validation.drift_ms == 0


def test_prompts_are_provider_neutral_complete_and_guard_historical_claims(tmp_path: Path) -> None:
    scenes, _, validation = generate_storyboard(_request(tmp_path))
    shot = scenes[0].shots[0]
    assert "Provider-neutral" in shot.prompts.core_prompt
    assert "modern objects" in shot.prompts.negative_prompt
    assert shot.reconstruction_status in {"PLAUSIBLE_RECONSTRUCTION", "SYMBOLIC"}
    assert validation.historical_status == "PASS"


def test_dialogue_metadata_and_subtitle_safety_are_preserved(tmp_path: Path) -> None:
    scenes, _, validation = generate_storyboard(_request(tmp_path))
    dialogue = [shot for scene in scenes for shot in scene.shots if shot.speaker_id == "historian"]
    assert dialogue
    assert all(shot.composition.subtitle_safe for shot in dialogue)
    assert all(shot.role == "HISTORICAL_CHARACTER" for shot in dialogue)
    assert validation.subtitle_safety_status == "PASS"


def test_asset_plan_has_map_document_and_cost_classes(tmp_path: Path) -> None:
    _, result, _ = generate_storyboard(_request(tmp_path))
    assets = json.loads(result.asset_plan_path.read_text(encoding="utf-8"))["assets"]
    assert any(asset["asset_type"] == "MAP" for asset in assets)
    assert any(asset["asset_type"] == "DOCUMENT" for asset in assets)
    assert {asset["generation_cost_class"] for asset in assets} <= {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}


def test_exports_bibles_manifest_and_markdown_are_written(tmp_path: Path) -> None:
    _, result, _ = generate_storyboard(_request(tmp_path))
    for path in (result.storyboard_path, result.markdown_path, result.asset_plan_path, result.character_bible_path, result.location_bible_path, result.validation_path, result.manifest_path):
        assert path.is_file() and path.stat().st_size > 0
    assert "# Production Storyboard v1" in result.markdown_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["render_readiness"] == "PASS"
    assert manifest["quality_score"] >= 80


def test_cache_is_deterministic_and_changed_config_invalidates(tmp_path: Path) -> None:
    request = _request(tmp_path)
    first_scenes, first, _ = generate_storyboard(request)
    second_scenes, second, _ = generate_storyboard(request)
    assert first.cache_hit is False and second.cache_hit is True
    assert first_scenes == second_scenes
    changed = _request(tmp_path, config=StoryboardConfig(pacing_profile="cinematic"))
    _, third, _ = generate_storyboard(changed)
    assert third.cache_hit is False


def test_render_timeline_is_episode_render_v2_compatible(tmp_path: Path) -> None:
    request = _request(tmp_path)
    scenes, _, _ = generate_storyboard(request)
    subtitles = json.loads(request.subtitle_manifest_path.read_text(encoding="utf-8"))
    timeline = render_timeline_from_storyboard(scenes, request.mastered_audio_path, subtitles)
    assert timeline["schema_version"] == "siraj-episode-render-manifest-v2"
    assert len(timeline["scenes"]) == len([shot for scene in scenes for shot in scene.shots])


def test_missing_or_mismatched_inputs_fail_early(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="STORYBOARD_MASTERED_AUDIO_NOT_FOUND"):
        generate_storyboard(StoryboardRequest(tmp_path / "missing.wav", tmp_path / "missing.json", tmp_path))
    audio, subtitles = _subtitle_manifest(tmp_path)
    data = json.loads(subtitles.read_text(encoding="utf-8")); data["source_audio_duration_ms"] = 1; subtitles.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="STORYBOARD_MASTERED_AUDIO_DURATION_MISMATCH"):
        generate_storyboard(StoryboardRequest(audio, subtitles, tmp_path / "out"))


def test_no_network_or_secret_content_is_emitted(tmp_path: Path) -> None:
    _, result, _ = generate_storyboard(_request(tmp_path))
    manifest = result.manifest_path.read_text(encoding="utf-8")
    assert "http://" not in manifest and "https://" not in manifest and "API_KEY" not in manifest
