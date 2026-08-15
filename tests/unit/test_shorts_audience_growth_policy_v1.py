from __future__ import annotations

from pathlib import Path

from src.application.shorts_burned_caption_engine_v1 import (
    MAX_LINES,
    _group_word_units,
    _wrap_text,
)
from src.application.shorts_derivative_engine_v1 import (
    Beat,
    Shot,
    _alignment_for_candidate,
    _vertical_reframe_for_shots,
    load_shorts_profile,
)

REPO = Path(__file__).resolve().parents[2]

def test_audience_growth_weights_are_exact_30_30_20_20() -> None:
    profile = load_shorts_profile(REPO)["profile"]
    weights = profile["scoring_weights"]
    nonzero = {key: value for key, value in weights.items() if float(value) != 0.0}
    assert nonzero == {
        "HOOK_STRENGTH": 0.30,
        "CURIOSITY": 0.30,
        "VERTICAL_COMPATIBILITY": 0.20,
        "LONGFORM_CONVERSION_POTENTIAL": 0.20,
    }
    assert profile["max_shorts_per_day"] == 2
    assert profile["audience_growth_policy"]["objective"] == "EXPAND_LONGFORM_AUDIENCE"

def test_missing_focus_geometry_becomes_reviewable_center_crop_not_reject() -> None:
    profile = load_shorts_profile(REPO)["profile"]
    shot = Shot(
        shot_id="S1", start_time=0.0, end_time=10.0, visual_action="",
        semantic_tags=(), subject_region=None, semantic_focus_region=None,
        safe_region=None, key_action_spans_full_width=False, unsafe_source=False,
        unsafe_background_face=False, face_enlarged_by_crop=False,
        vertical_quality_hint=None,
    )
    result = _vertical_reframe_for_shots((shot,), source_aspect=16/9, profile=profile)
    assert result["status"] == "PASS"
    item = result["shots"][0]
    assert item["tracking_mode"] == "STATIC_CENTER_FALLBACK"
    assert item["human_final_visual_review_required"] is True
    assert item["semantic_focus_region"] is None

def test_missing_visual_action_is_review_required_not_contradiction() -> None:
    beat = Beat(
        beat_id="B1", start_time=0.0, end_time=5.0, text="كيف بدأت القصة؟",
        chapter_id="C1", shot_ids=("S1",), claim_ids=(), narrative_role="QUESTION",
        context_dependencies=(), character_refs=(), visual_action="", semantic_payload={},
        curiosity_signal=1.0, surprise_signal=0.0, emotional_signal=0.0,
        story_turn_signal=0.0, revelation_signal=0.0, question_signal=1.0,
        payoff_signal=0.0, standalone_potential=0.5, visual_strength_indicators=(),
    )
    shot = Shot(
        shot_id="S1", start_time=0.0, end_time=5.0, visual_action="",
        semantic_tags=(), subject_region=None, semantic_focus_region=None,
        safe_region=None, key_action_spans_full_width=False, unsafe_source=False,
        unsafe_background_face=False, face_enlarged_by_crop=False,
        vertical_quality_hint=None,
    )
    class Episode:
        pass
    result = _alignment_for_candidate(Episode(), (beat,), (shot,))
    assert result["status"] == "PASS"
    assert result["findings"] == []
    assert result["human_final_visual_review_required"] is True

def test_word_timing_splits_long_arabic_into_multiple_two_line_cues() -> None:
    words = [
        "هذا", "اختبار", "طويل", "للتأكد", "من", "أن", "النص", "الموثوق",
        "ينقسم", "إلى", "عدة", "مقاطع", "قصيرة", "بدون", "حذف", "أي",
        "كلمة", "من", "التعليق", "الصوتي",
    ]
    parent = " ".join(words)
    units = [
        {
            "segment_id": f"W{index:03d}",
            "parent_segment_id": "P1",
            "parent_text": parent,
            "start_seconds": index * 0.2,
            "end_seconds": index * 0.2 + 0.18,
            "text": word,
            "timing_authority": "WORD_BOUNDARY",
            "text_provenance": "NARRATION_ONLY",
        }
        for index, word in enumerate(words)
    ]
    grouped = _group_word_units(units)
    assert len(grouped) > 1
    assert all(len(_wrap_text(item["text"])) <= MAX_LINES for item in grouped)
    assert " ".join(item["text"] for item in grouped) == parent
