from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from src.application.local_semantic_intelligence.semantic_acceptance_gate import (
    MATN_BOUNDARY_CONTRACT,
    build_context_window,
    evaluate_semantic_acceptance,
    validate_matn_boundary,
)


FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "semantic_acceptance"
    / "4445-6244.json"
)


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_4445_6244_blocks_invalid_boundary_and_incomplete_isnad() -> None:
    fixture = _fixture()
    original_output = deepcopy(fixture["provider_output"])

    result = evaluate_semantic_acceptance(
        fixture["original_text"],
        fixture["route"],
        fixture["provider_output"],
    )

    assert fixture["provider_output"] == original_output
    assert result["status"] == "FAIL"
    assert result["production_acceptance"] == "BLOCKED"
    assert result["human_review_required"] is True
    assert result["repair_count"] == 2
    assert result["rejection_count"] == 0
    assert result["matn_boundary_contract"] == MATN_BOUNDARY_CONTRACT
    assert result["matn_boundary_error_count"] == 1
    assert (
        result["matn_boundary_checks"][0]["reason_code"]
        == "MATN_BOUNDARY_GRAPHEME_SPLIT"
    )

    completeness = result["isnad_completeness"]
    assert completeness["status"] == "PARTIAL"
    assert completeness["candidate_count"] == 3
    assert completeness["covered_candidate_count"] == 1
    assert completeness["uncovered_candidate_count"] == 2
    assert {
        item["cue_type"]
        for item in completeness["uncovered_candidates"]
    } == {"ABRIDGED_REPORT", "ATTRIBUTED_REPORT"}

    repaired = result["repaired_output"]
    expected_surface = (
        "أَبُو بَكْرِ بْنُ عَبْدِ اللَّهِ "
        "بْنِ أَبِي سَبْرَةَ"
    )
    assert repaired["entities"][1]["surface"] == expected_surface
    assert (
        repaired["entities"][1]["evidence"]["text"]
        == expected_surface
    )
    assert all(
        quote["text"] in fixture["original_text"]
        for quote in result["evidence_quotes"]
    )


def test_matn_boundary_contract_accepts_token_start() -> None:
    fixture = _fixture()
    quote = fixture["original_text"][
        fixture["original_text"].index("قَالَ الْوَاقِدِيُّ"):
        fixture["original_text"].index(
            " قُلْتُ: أَيْنَ دُفِنَ؟"
        )
    ]
    boundary = quote.index("سَأَلْتُ")

    result = validate_matn_boundary(quote, boundary)

    assert result["status"] == "VALID"
    assert result["reason_code"] == ""
    assert result["contract"] == MATN_BOUNDARY_CONTRACT


def test_context_window_keeps_target_provenance_explicit() -> None:
    window = build_context_window(
        "previous-" * 200,
        "TARGET",
        "next-" * 200,
        previous_tail_characters=12,
        next_head_characters=10,
    )

    assert window["target_text"] == "TARGET"
    assert len(window["previous_context"]) == 12
    assert len(window["next_context"]) == 10
    assert (
        window["evidence_policy"]
        == "TARGET_TEXT_ONLY_UNLESS_CROSS_PAGE_EXPLICIT"
    )
    assert window["cross_page_items_require_explicit_marker"] is True
