from __future__ import annotations

from copy import deepcopy

import pytest

from src.application.shorts_conversion_director_v1 import (
    CONVERSION_GATE_NAMES,
    CONVERSION_SIGNAL_FIELDS,
    ConversionDirector,
    ConversionDirectorError,
    ShortsConversionDirector,
    account_portfolio,
    build_endpoint_variants,
    score_candidate,
    select_endpoint_variant,
)


def _candidate(
    candidate_id: str = "EP-001-SHORT-001",
    *,
    hook: float = 0.90,
    retention: float = 0.85,
    standalone: float = 0.90,
    open_loop: float = 0.80,
    conversion: float = 0.86,
    spoiler: float = 0.25,
    payoff: float = 0.20,
    **extra,
) -> dict:
    value = {
        "candidate_id": candidate_id,
        "episode_id": "EP-001",
        "source_episode_sha256": "a" * 64,
        "total_score": 0.88,
        "score_breakdown": {
            "HOOK_STRENGTH": {"value": hook},
            "RETENTION_POTENTIAL": {"value": retention},
            "STANDALONE_CLARITY": {"value": standalone},
        },
        "longform_conversion_score": conversion,
        "spoiler_cost": spoiler,
        "payoff_disclosure_level": payoff,
        "context_dependence_score": 0.10,
        "missing_context_items": [],
        "cta_plan": {"mode": "NATURAL_OPEN_LOOP", "source_derived": True},
        "open_loop_strength": open_loop,
        "source_claim_ids": [candidate_id + "-claim"],
        "payoff_claim_ids": [candidate_id + "-payoff"],
    }
    value.update(extra)
    return value


def test_required_conversion_signals_and_gates_are_serialized() -> None:
    result = score_candidate(_candidate())

    assert set(CONVERSION_SIGNAL_FIELDS).issubset(result)
    assert set(CONVERSION_GATE_NAMES) == set(result["gates"])
    assert result["SOURCE_EPISODE_ID"] == "EP-001"
    assert result["CONVERSION_BRIDGE_STATUS"] == "PASS"
    assert result["CONVERSION_BRIDGE_REASON"]
    assert result["WITHHELD_PAYOFF_SUMMARY"]["text"] is None
    assert result["evaluation_sha256"]


def test_strong_hook_withheld_payoff_is_rankable() -> None:
    result = score_candidate(_candidate())

    assert result["status"] == "PASS"
    assert result["HOOK_STRENGTH"] == 0.90
    assert result["OPEN_LOOP_STRENGTH"] == 0.80
    assert result["SPOILER_COST"] == 0.25
    assert result["PAYOFF_OVERDISCLOSURE"] is False
    assert result["rank_score"] > 0.70


def test_full_payoff_is_penalized_but_not_hard_rejected_for_teaser() -> None:
    full_payoff = _candidate(
        "EP-001-FULL",
        open_loop=0.02,
        conversion=0.40,
        spoiler=0.96,
        payoff=0.96,
    )
    strong = _candidate("EP-001-STRONG")
    director = ConversionDirector()

    evaluated = director.score_candidate(full_payoff)
    strong_eval = director.score_candidate(strong)
    ranked = director.rank_candidates([full_payoff, strong])

    # Audience-growth policy: a complete payoff may still be usable, but a
    # stronger curiosity/conversion teaser must rank above it.
    assert evaluated["status"] == "PASS"
    assert evaluated["rank_score"] < strong_eval["rank_score"]
    assert ranked[0]["candidate_id"] == "EP-001-STRONG"

@pytest.mark.parametrize(
    ("gate", "field"),
    [
        ("MISLEADING_OPEN_LOOP", "misleading_open_loop"),
        ("FABRICATED_CURIOSITY", "fabricated_curiosity"),
        ("SHORT_SUMMARIZES_WHOLE_ANSWER", "short_summarizes_whole_answer"),
        ("NO_REASON_TO_WATCH_LONGFORM", "no_reason_to_watch_longform"),
        ("CONTEXT_REQUIRED_BUT_MISSING", "context_required_but_missing"),
    ],
)
def test_explicit_conversion_gates_fail_closed(gate: str, field: str) -> None:
    candidate = _candidate(**{field: True})
    if gate == "NO_REASON_TO_WATCH_LONGFORM":
        candidate["open_loop_strength"] = 0.05
        candidate["payoff_disclosure_level"] = 0.20
        candidate["spoiler_cost"] = 0.20
    result = score_candidate(candidate)

    assert result["status"] == "REJECTED"
    assert gate in result["rejection_reasons"]
    assert result["gates"][gate]["status"] == "FAIL"


def test_context_items_are_not_silently_repaired() -> None:
    result = score_candidate(
        _candidate(
            context_dependence_score=0.65,
            missing_context_items=["DEFERRED_REFERENCE"],
        )
    )

    assert result["status"] == "REJECTED"
    assert "CONTEXT_REQUIRED_BUT_MISSING" in result["rejection_reasons"]


def test_generated_cta_is_treated_as_fabricated_curiosity() -> None:
    result = score_candidate(
        _candidate(
            cta_plan={"mode": "GENERATED_CTA", "text": "Watch the full episode", "source_derived": False}
        )
    )

    assert result["status"] == "REJECTED"
    assert "FABRICATED_CURIOSITY" in result["rejection_reasons"]


def test_structured_gate_receipts_are_enforced_without_boolean_shortcuts() -> None:
    result = score_candidate(
        _candidate(
            conversion_gates={
                "MISLEADING_OPEN_LOOP": {"status": "FAIL", "evidence": ["source_open_loop_receipt"]}
            }
        )
    )

    assert result["status"] == "REJECTED"
    assert result["gates"]["MISLEADING_OPEN_LOOP"]["evidence"] == ["misleading_open_loop"]


def test_endpoint_variants_use_only_semantic_source_boundaries() -> None:
    candidate = _candidate(start_time=0.0, end_time=15.0)
    segments = [
        {"segment_id": "S1", "start": 0.0, "end": 5.0, "text": "A question begins.", "sentence_boundary": True, "semantic_complete": True, "open_loop_strength": 0.80, "spoiler_cost": 0.20, "payoff_disclosure_level": 0.20},
        {"segment_id": "S2", "start": 5.0, "end": 10.0, "text": "The middle continues", "sentence_boundary": False, "semantic_complete": False},
        {"segment_id": "S3", "start": 10.0, "end": 15.0, "text": "but no conclusion is invented.", "sentence_boundary": True, "semantic_complete": True, "open_loop_strength": 0.75, "spoiler_cost": 0.30, "payoff_disclosure_level": 0.25},
    ]

    variants = build_endpoint_variants(candidate, source_segments=segments)
    selected = select_endpoint_variant(candidate, variants)

    assert variants
    assert all(item["source_derived"] is True for item in variants)
    assert all(item["semantic_complete"] is True for item in variants)
    assert selected["selection_status"] == "PASS"
    assert selected["source_segment_ids"] == ["S1"]
    assert "Watch" not in selected["text"]


def test_missing_endpoint_evidence_blocks_instead_of_guessing() -> None:
    blocked = build_endpoint_variants(_candidate(start_time=0.0, end_time=120.0))

    assert blocked[0]["status"] == "BLOCKED"
    assert blocked[0]["source_derived"] is False


def test_portfolio_accounts_cumulative_spoiler_and_downselects_summary_risk() -> None:
    candidates = [
        _candidate("C1", spoiler=0.35, payoff=0.35, source_claim_ids=["CLAIM-1"], payoff_claim_ids=["PAYOFF-1"]),
        _candidate("C2", spoiler=0.35, payoff=0.35, source_claim_ids=["CLAIM-2"], payoff_claim_ids=["PAYOFF-2"]),
        _candidate("C3", spoiler=0.35, payoff=0.35, source_claim_ids=["CLAIM-3"], payoff_claim_ids=["PAYOFF-3"]),
    ]

    result = account_portfolio(candidates, selected_candidate_ids=["C1", "C2", "C3"])

    assert result["selected_candidate_ids"] == ["C1", "C2"]
    assert result["downselected_candidate_ids"] == ["C3"]
    assert result["CUMULATIVE_SPOILER_COST"] == 0.70
    assert result["CUMULATIVE_PAYOFF_COVERAGE"] == 0.70
    assert result["PORTFOLIO_SUMMARIZES_WHOLE_EPISODE"] is True
    assert result["status"] == "DOWNSELECT_REQUIRED"


def test_portfolio_deduplicates_shared_source_claim_contribution() -> None:
    candidates = [
        _candidate("C1", spoiler=0.40, payoff=0.40, source_claim_ids=["CLAIM-1"], payoff_claim_ids=["PAYOFF-1"]),
        _candidate("C2", spoiler=0.40, payoff=0.40, source_claim_ids=["CLAIM-1"], payoff_claim_ids=["PAYOFF-1"]),
    ]

    result = account_portfolio(candidates, selected_candidate_ids=["C1", "C2"])

    assert result["selected_candidate_ids"] == ["C1", "C2"]
    assert result["CUMULATIVE_SPOILER_COST"] == 0.40
    assert result["CUMULATIVE_PAYOFF_COVERAGE"] == 0.40


def test_director_is_deterministic_and_does_not_mutate_input() -> None:
    candidate = _candidate()
    original = deepcopy(candidate)
    director = ConversionDirector()

    first = director.score_candidate(candidate)
    second = director.score_candidate(candidate)

    assert first == second
    assert candidate == original


def test_unknown_episode_is_blocked_and_strict_mode_can_raise() -> None:
    result = score_candidate({"candidate_id": "NO-SOURCE"})
    assert result["status"] == "BLOCKED"
    assert result["SOURCE_EPISODE_ID"] == "UNKNOWN"

    with pytest.raises(ConversionDirectorError):
        ConversionDirector(strict=True).evaluate_candidate({"candidate_id": "NO-SOURCE"})


def test_unknown_candidate_id_in_requested_portfolio_is_rejected() -> None:
    with pytest.raises(ConversionDirectorError, match="CANDIDATE_UNKNOWN"):
        account_portfolio([_candidate("C1")], selected_candidate_ids=["C2"])


def test_desktop_compatibility_alias_delegates_existing_apis() -> None:
    candidate = _candidate()
    director = ShortsConversionDirector()

    assessed = director.assess_candidate(candidate)
    scored = director.score_candidate(candidate)
    selected = director.select_portfolio([candidate], selected_candidate_ids=[candidate["candidate_id"]])
    evaluated = director.evaluate_portfolio([candidate], selected_candidate_ids=[candidate["candidate_id"]])

    assert assessed.to_dict() == scored
    assert selected == evaluated
    assert selected["selected_candidate_ids"] == [candidate["candidate_id"]]
