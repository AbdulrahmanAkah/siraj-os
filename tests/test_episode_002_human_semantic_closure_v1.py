from __future__ import annotations

from pathlib import Path

from src.application.episode_002_human_semantic_closure_v1 import (
    build_closure_review,
    build_promotion_proposal,
)


REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"


def test_closure_review_uses_unambiguous_generic_regression_semantics_and_does_not_promote():
    review = build_closure_review(REPO, EPISODE)
    assert review["report_inconsistency"]["status"] == "FIXED"
    assert review["report_inconsistency"]["historical_reports_modified"] is False
    assert review["candidate_promoted"] is False
    assert review["authoritative_alignment_modified"] is False
    assert review["structural_validation"]["structural_fingerprint"] == "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
    for finding in review["semantic_closure_findings"]:
        assert finding["generic_prompt_regression_check"] == "EXECUTED"
        assert finding["generic_prompt_regression_detected"] is False
        assert finding["recommendation"] == "HUMAN_CLOSE_RECOMMENDED"


def test_gate_is_separate_and_promotion_plan_is_proposal_only():
    review = build_closure_review(REPO, EPISODE)
    gate = review["gate_001"]
    assert gate["owner"] == "DOWNSTREAM_GATE"
    assert gate["required_stage"] == "PROMPT_SIMILARITY_AND_DUPLICATE_GATE"
    assert gate["closed"] is False
    assert gate["can_evaluate_before_promotion"] is False
    assert gate["can_evaluate_after_promotion"] is True
    proposal = build_promotion_proposal(REPO, EPISODE, review)
    assert proposal["status"] == "PROPOSED_NOT_APPROVED_NOT_APPLIED"
    assert proposal["candidate_promoted"] is False
    assert proposal["authorizes_promotion"] is False
    assert proposal["bundled_provider_or_media_execution"] is False
    assert len(proposal["modified_shot_ids"]) == 29


def test_v2_warns_for_intentional_motif_density_without_significant_regression():
    review = build_closure_review(REPO, EPISODE)
    assert review["v2_candidate_review"]["status"] == "WARN"
    assert review["v2_candidate_review"]["significant_regression"] is False
    assert review["v2_candidate_review"]["cross_sequence_similarity"] == []
