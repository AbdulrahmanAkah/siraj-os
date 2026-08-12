from __future__ import annotations

from pathlib import Path

import pytest

from src.application.preserved_alignment_candidate_salvage_v1 import derive_salvage_view
from src.application.siraj_cinematic_director_v2 import (
    CinematicDirectorV2Error,
    cross_sequence_distinctness,
    evaluate_v1_compatibility,
    fresh_episode_initialization,
    prose_image_gap_check,
    renderability_check,
    scale_diversity_check,
    validate_v2_direction,
    validate_sequence_grammar,
)
from src.application.cinematic_director_v2_reporting_v1 import build_v2_reports


REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"


def _candidate_directions():
    view = derive_salvage_view(REPO, EPISODE)
    changed = {patch["shot_id"] for patch in view["patches"]}
    return [
        direction for direction in view["candidate_overlay"]["directions"]
        if direction["shot_id"] in changed
    ]


def test_v2_is_backward_compatible_with_preserved_v1_candidate_and_never_calls_provider():
    result = evaluate_v1_compatibility(_candidate_directions())
    assert result["direction_count"] == 29
    assert result["v1_roundtrip_compatible"] is True
    assert result["structural_ownership_preserved"] is True
    assert result["provider_calls"] == 0


def test_v2_rejects_structural_mutation():
    direction = dict(_candidate_directions()[0])
    direction["start_seconds"] = 0
    with pytest.raises(CinematicDirectorV2Error, match="STRUCTURAL_FIELD_FORBIDDEN"):
        validate_v2_direction(direction)


def test_next_episode_starts_fresh_without_episode_002_grammar_or_motifs():
    contract = fresh_episode_initialization("episode-003")
    assert contract["cinematic_mode"] == "NATIVE_SIRAJ_CINEMATIC_DIRECTOR_V2"
    assert contract["creative_initialization"] == "FRESH_EPISODE"
    assert contract["episode_002_visual_grammar_inherited"] is False
    assert contract["episode_002_motifs_inherited"] is False
    assert contract["provider_calls_by_default"] == 0


def test_v2_quality_checks_detect_generic_and_prose_image_gap_without_provider():
    generic = {"shot_id": "X", "visual_concept": "cinematic historical scene", "cinematic_treatment": "word " * 50}
    assert "GENERIC_PROMPT_REGRESSION" in renderability_check(generic)
    assert prose_image_gap_check(generic) == "WARN_PROSE_IMAGE_GAP"


def test_cross_sequence_duplicate_signature_and_scale_monotony_are_detected():
    direction = {"shot_id": "X", "visual_concept": "wide stone plain", "environment": "stone", "camera_intent": "wide", "lighting": "dawn"}
    warnings = cross_sequence_distinctness({"A": [direction], "B": [dict(direction, shot_id="Y")]})
    assert warnings == [{"left": "B", "right": "A", "issue": "IDENTICAL_VISUAL_SIGNATURE"}]
    assert scale_diversity_check([direction, dict(direction, shot_id="Y"), dict(direction, shot_id="Z")])["status"] == "WARN"


def test_sequence_visual_grammar_requires_full_typed_contract():
    with pytest.raises(CinematicDirectorV2Error, match="SEQUENCE_VISUAL_GRAMMAR_FIELDS_REQUIRED"):
        validate_sequence_grammar({"sequence_id": "A"})


def test_v2_selective_review_preserves_all_paid_candidate_shots_by_default():
    report = build_v2_reports(REPO, EPISODE)
    review = report["selective_review"]
    assert review["shots_reviewed"] == 29
    assert review["keep_existing_count"] == 29
    assert review["selective_v2_enhancement_recommended_count"] == 0
    assert review["patched_count"] == 0
    assert report["candidate_promoted"] is False
    assert report["next_episode_fresh_start"]["episode_002_visual_grammar_inherited"] is False
