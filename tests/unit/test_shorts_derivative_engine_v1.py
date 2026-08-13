from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.shorts_derivative_desktop_integration_v1 import desktop_workflow_descriptor
from src.presentation.desktop.shorts_derivative_dock_v1 import desktop_dock_descriptor
from src.application.shorts_derivative_engine_v1 import (
    HashBoundCache,
    ShortsBlockedError,
    ShortsDerivativeEngine,
    approve_local_render,
    build_vertical_reframe_plan,
    captions_to_srt,
    captions_to_vtt,
    capability_boundary_evidence,
    create_human_review_receipt,
    load_shorts_profile,
    select_portfolio,
    validate_extractive_reorder,
)


REPO = Path(__file__).resolve().parents[2]


def _episode_metadata(*, unsafe_face: bool = False, context_dependent: bool = False, full_width: bool = False) -> dict:
    first_text = "As mentioned, he opened the door." if context_dependent else "What changed when the door opened?"
    return {
        "episode_id": "FIXTURE-EPISODE-001",
        "constitution_version": "1.0.0",
        "duration_seconds": 15.0,
        "source_certainty": "VERIFIED",
        "wardrobe_contract_id": "WARDROBE-FIXTURE-001",
        "period_dossier_id": "PERIOD-FIXTURE-001",
        "canonical_reference_sha256": "a" * 64,
        "narration_master_sha256": "b" * 64,
        "claims": [],
        "segments": [
            {"segment_id": "SEG-1", "start": 0, "end": 5, "text": first_text},
            {"segment_id": "SEG-2", "start": 5, "end": 10, "text": "The answer was hidden in the first light."},
            {"segment_id": "SEG-3", "start": 10, "end": 15, "text": "The lesson remained larger than the moment."},
        ],
        "beats": [
            {
                "beat_id": "BEAT-1",
                "start": 0,
                "end": 5,
                "text": first_text,
                "narrative_role": "QUESTION",
                "shot_ids": ["SHOT-1"],
                "visual_action": "A covered figure opens an ancient wooden door",
                "visual_strength_indicators": ["clear_action", "high_contrast"],
                "question_signal": 1.0,
            },
            {
                "beat_id": "BEAT-2",
                "start": 5,
                "end": 10,
                "text": "The answer was hidden in the first light.",
                "narrative_role": "REVELATION",
                "shot_ids": ["SHOT-2"],
                "visual_action": "Warm light crosses the room and reveals the path",
                "visual_strength_indicators": ["revealing_light", "clear_direction"],
                "revelation_signal": 1.0,
                "payoff_signal": 0.8,
            },
            {
                "beat_id": "BEAT-3",
                "start": 10,
                "end": 15,
                "text": "The lesson remained larger than the moment.",
                "narrative_role": "REFLECTION",
                "shot_ids": ["SHOT-3"],
                "visual_action": "The path continues beyond the doorway",
                "visual_strength_indicators": ["depth", "continuation"],
                "payoff_signal": 0.3,
            },
        ],
        "shots": [
            {
                "shot_id": "SHOT-1",
                "start": 0,
                "end": 5,
                "visual_action": "A covered figure opens an ancient wooden door",
                "subject_region": {"x": 0.12, "y": 0.2, "w": 0.22, "h": 0.55},
                "semantic_focus_region": {"x": 0.12, "y": 0.2, "w": 0.22, "h": 0.55},
                "safe_region": {"x": 0.05, "y": 0.1, "w": 0.45, "h": 0.8},
                "unsafe_source": unsafe_face,
                "unsafe_background_face": False,
                "face_enlarged_by_crop": False,
                "key_action_spans_full_width": full_width,
            },
            {
                "shot_id": "SHOT-2",
                "start": 5,
                "end": 10,
                "visual_action": "Warm light crosses the room and reveals the path",
                "subject_region": {"x": 0.62, "y": 0.2, "w": 0.2, "h": 0.5},
                "semantic_focus_region": {"x": 0.62, "y": 0.2, "w": 0.2, "h": 0.5},
                "safe_region": {"x": 0.52, "y": 0.1, "w": 0.45, "h": 0.8},
            },
            {
                "shot_id": "SHOT-3",
                "start": 10,
                "end": 15,
                "visual_action": "The path continues beyond the doorway",
                "subject_region": {"x": 0.42, "y": 0.25, "w": 0.18, "h": 0.45},
                "semantic_focus_region": {"x": 0.42, "y": 0.25, "w": 0.18, "h": 0.45},
                "safe_region": {"x": 0.3, "y": 0.1, "w": 0.4, "h": 0.8},
            },
        ],
    }


def _fixture_engine(tmp_path: Path, **metadata_flags):
    engine = ShortsDerivativeEngine(REPO)
    source = tmp_path / "fixture-source.mp4"
    source.write_bytes(b"deterministic fixture source bytes")
    metadata = tmp_path / "fixture-metadata.json"
    metadata.write_text(json.dumps(_episode_metadata(**metadata_flags), ensure_ascii=False), encoding="utf-8")
    episode = engine.ingest(
        mode="VIDEO_PLUS_TRANSCRIPT",
        video_path=source,
        metadata_path=metadata,
    )
    return engine, episode


def test_profile_is_versioned_and_fail_closed() -> None:
    profile = load_shorts_profile(REPO)
    assert profile["profile"]["profile_id"] == "SIRAJ_SHORTS_DERIVATIVE_PROFILE_V1"
    assert profile["profile"]["max_shorts_per_day"] == 1
    assert profile["profile"]["music"] is False
    assert profile["profile"]["no_silent_defaults"] is True


def test_ingestion_is_hash_bound_and_read_only(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path)
    before = episode.source_episode_sha256
    analysis = engine.analyze(episode)
    assert episode.source_episode_sha256 == before
    assert analysis.episode.source_episode_sha256 == before
    assert analysis.episode.source_metadata_hashes
    assert analysis.episode.legacy_source is False


def test_candidate_discovery_finds_question_answer_and_revelation(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path)
    analysis = engine.analyze(episode)
    types = {candidate.candidate_type for candidate in analysis.candidates}
    assert "QUESTION_ANSWER" in types or "CURIOSITY" in types
    assert "REVELATION" in types
    assert all(candidate.source_episode_sha256 == episode.source_episode_sha256 for candidate in analysis.candidates)
    assert all("value" in dimension.to_dict() for candidate in analysis.candidates for dimension in candidate.score_breakdown.values())


def test_context_dependent_candidate_is_penalized(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path, context_dependent=True)
    analysis = engine.analyze(episode)
    dependent = [candidate for candidate in analysis.candidates if "PRONOUN" in candidate.missing_context_items or "DEFERRED_REFERENCE" in candidate.missing_context_items]
    assert dependent
    assert all(candidate.context_dependence_score > 0 for candidate in dependent)
    assert any(candidate.status != "PASS" for candidate in dependent)


def test_constitutional_face_failure_cannot_be_overridden_by_score(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path, unsafe_face=True)
    analysis = engine.analyze(episode)
    assert any(candidate.status != "PASS" for candidate in analysis.candidates)
    assert any("FAIL_GLOBAL_FACE_POLICY" in candidate.policy_result.get("errors", ()) or "SHORT_CONSTITUTION_SCOPE_BLOCKED" in candidate.rejection_reasons for candidate in analysis.candidates)
    with pytest.raises(ShortsBlockedError, match="CANNOT_OVERRIDE"):
        select_portfolio(analysis, candidate_ids=[analysis.candidates[-1].candidate_id], human_selection_reviewed=True)


def test_vertical_reframe_is_left_or_right_aware_and_not_face_tracking(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path)
    plan = build_vertical_reframe_plan(episode, ["SHOT-1", "SHOT-2"], engine.profile)
    assert plan["status"] == "PASS"
    assert plan["face_tracking_dependency"] is False
    assert plan["shots"][0]["crop_window"]["x"] < 0.2
    assert plan["shots"][1]["crop_window"]["x"] > 0.2


def test_full_width_vertical_action_is_rejected(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path, full_width=True)
    analysis = engine.analyze(episode)
    assert any(candidate.status != "PASS" for candidate in analysis.candidates)
    assert any("SHORT_VERTICAL_QUALITY_FAIL" in candidate.rejection_reasons or candidate.vertical_reframe_plan["status"] != "PASS" for candidate in analysis.candidates)


def test_extractive_reorder_preserves_chronology_only() -> None:
    from src.application.shorts_derivative_engine_v1 import Beat

    beats = (
        Beat("A", 0, 1, "first", "C", (), (), "SETUP", (), (), "action", {}, 0, 0, 0, 0, 0, 0, 0, 1, ()),
        Beat("B", 1, 2, "then", "C", (), (), "PAYOFF", (), (), "action", {}, 0, 0, 0, 0, 0, 0, 1, 1, ()),
    )
    assert validate_extractive_reorder(beats, ["A", "B"])["status"] == "PASS"
    assert validate_extractive_reorder(beats, ["B", "A"])["status"] == "FAIL"


def test_portfolio_is_dynamic_and_schedule_only_blocks_without_publish_day(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path)
    analysis = engine.analyze(episode)
    portfolio = engine.portfolio(analysis, human_selection_reviewed=True)
    assert portfolio.schedule_status == "BLOCKED_MISSING_LONGFORM_DAY"
    assert len(portfolio.selected_candidate_ids) <= 6
    assert portfolio.portfolio_status == "PORTFOLIO_READY"
    assert len(set(portfolio.recommended_order)) == len(portfolio.recommended_order)


def test_render_plan_requires_human_selection_and_click(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path)
    analysis = engine.analyze(episode)
    portfolio = engine.portfolio(analysis, candidate_ids=[analysis.candidates[0].candidate_id], human_selection_reviewed=False)
    with pytest.raises(ShortsBlockedError, match="SELECTION_REVIEW_REQUIRED|PORTFOLIO_HUMAN"):
        engine.render_plan(analysis, portfolio, analysis.candidates[0].candidate_id, human_selection_approved=False)
    approved_portfolio = engine.portfolio(analysis, candidate_ids=[analysis.candidates[0].candidate_id], human_selection_reviewed=True)
    plan = engine.render_plan(analysis, approved_portfolio, analysis.candidates[0].candidate_id, human_selection_approved=True)
    assert plan.local_render_approved is False
    with pytest.raises(ShortsBlockedError):
        approve_local_render(plan, explicit_human_click=False)
    assert approve_local_render(plan, explicit_human_click=True).local_render_approved is True


def test_captions_are_external_only() -> None:
    plan = {"burned_captions": False, "cues": [{"start": 0, "end": 1, "text": "source", "beat_id": "B1"}]}
    assert "WEBVTT" in captions_to_vtt(plan)
    assert "00:00:00,000 --> 00:00:01,000" in captions_to_srt(plan)


def test_hash_bound_cache_invalidates_stale_source() -> None:
    cache = HashBoundCache()
    first = "a" * 64
    second = "b" * 64
    cache.put("map", first, {"ok": True})
    assert cache.get("map", first) == {"ok": True}
    assert cache.get("map", second) is None
    assert cache.invalidate(second) == ["map"]


def test_capability_boundary_has_no_provider_or_network_imports() -> None:
    evidence = capability_boundary_evidence(REPO / "src/application/shorts_derivative_engine_v1.py")
    assert evidence["pass"] is True
    assert evidence["short_analyzer_can_call_provider"] is False
    assert evidence["shorts_engine_can_upload_youtube"] is False


def test_desktop_descriptor_is_actionable_but_never_publication() -> None:
    descriptor = desktop_workflow_descriptor()
    assert "Analyze Episode" in descriptor["actions"]
    assert descriptor["boundaries"]["automatic_publication"] is False
    assert descriptor["boundaries"]["public_title_owner"] == "HUMAN"


def test_existing_desktop_dock_is_single_workflow_and_fail_closed() -> None:
    descriptor = desktop_dock_descriptor()
    assert descriptor["existing_gui"] is True
    assert descriptor["second_gui_created"] is False
    assert "Generate Local Render Plans" in descriptor["actions"]
    assert descriptor["hard_boundaries"]["automatic_publication"] is False


def test_legacy_source_is_analyzed_but_not_grandfathered(tmp_path: Path) -> None:
    engine, episode = _fixture_engine(tmp_path)
    metadata_path = tmp_path / "legacy.json"
    metadata = _episode_metadata()
    metadata["constitution_version"] = "0.9.0"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    legacy = engine.ingest(mode="VIDEO_PLUS_TRANSCRIPT", video_path=Path(episode.source_video_path), metadata_path=metadata_path)
    assert legacy.legacy_source is True
    analysis = engine.analyze(legacy)
    assert all(candidate.policy_result.get("legacy_recheck_required") is True for candidate in analysis.candidates)
    assert all(candidate.policy_result.get("legacy_rechecked") is True for candidate in analysis.candidates)
