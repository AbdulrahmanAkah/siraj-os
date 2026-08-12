from __future__ import annotations

from pathlib import Path

from src.application.alignment_finding_ownership_v1 import (
    FindingOwner,
    classify_alignment_finding,
    editable_finding_ids,
)
from src.application.controlled_alignment_reporting_v1 import (
    render_controlled_alignment_markdown,
)
from src.application.controlled_alignment_validation_v1 import (
    _candidate_overlay,
    _preflight,
    _request_payload,
    _validate_response,
)
from src.application.preserved_alignment_candidate_salvage_v1 import (
    EXPECTED_CANDIDATE_SHA256,
    derive_salvage_view,
)


REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"


def test_episode_002_finding_ownership_excludes_local_gate_from_luna_editable_scope():
    assert classify_alignment_finding("LUNA-GATE-001") is FindingOwner.DOWNSTREAM_GATE
    assert editable_finding_ids(
        ["LUNA-SEM-001", "LUNA-REP-001", "LUNA-GATE-001"]
    ) == ["LUNA-SEM-001", "LUNA-REP-001"]
    state = _preflight(REPO, EPISODE)
    payload = _request_payload(state, "gpt-5.6-luna")
    body = payload["input"][1]["content"][0]["text"]
    assert "editable_semantic_findings" in body
    assert '"finding_id":"LUNA-GATE-001","owner":"DOWNSTREAM_GATE","instruction":"DO_NOT_RESOLVE"' in body


def test_local_gate_resolution_is_preserved_but_ignored_for_semantic_candidate_scoring():
    state = _preflight(REPO, EPISODE)
    import json
    from src.application.controlled_alignment_validation_v1 import _parse_model_json

    record = json.loads(
        (REPO / "projects" / EPISODE / "orchestration" / "controlled-alignment-validation-v1" / "provider-proposal.json").read_text(encoding="utf-8-sig")
    )
    response = _parse_model_json(record["output_text"])
    validation = _validate_response(state, response)
    assert validation["classification"] == "OBJECTIVE_IMPROVEMENT"
    assert validation["protocol_violations"][0]["finding_id"] == "LUNA-GATE-001"
    assert validation["protocol_violations"][0]["semantic_scoring"] == "IGNORED"
    candidate, _, _ = _candidate_overlay(state, response)
    from src.application.artifact_provenance_v1 import canonical_sha256

    assert canonical_sha256(candidate) == EXPECTED_CANDIDATE_SHA256


def test_preserved_candidate_salvage_is_derived_and_non_promoting():
    view = derive_salvage_view(REPO, EPISODE)
    assert view["candidate_sha256"] == EXPECTED_CANDIDATE_SHA256
    assert view["candidate_patch_count"] == 29
    assert view["salvage_classification"] == "SALVAGE_OBJECTIVE_IMPROVEMENT"
    assert view["local_gate_001"]["luna_resolution_ignored"] is True
    assert view["candidate_promoted"] is False
    assert view["authoritative_alignment_modified"] is False
    assert view["creative_validation"]["generic_prompt_regression_check"] == "EXECUTED"
    assert view["creative_validation"]["generic_prompt_regression_detected"] is False
    for finding in view["semantic_findings"]:
        evidence = finding["local_evidence"]
        assert evidence["generic_prompt_regression_check"] == "EXECUTED"
        assert evidence["generic_prompt_regression_detected"] is False
        assert "generic_prompt_regression" not in evidence


def test_future_report_renderer_never_leaves_creative_baseline_placeholder():
    rendered = render_controlled_alignment_markdown(
        {
            "classification": "SALVAGE_OBJECTIVE_IMPROVEMENT",
            "creative_baseline_hash": "a" * 64,
            "candidate_sha256": "b" * 64,
        }
    )
    assert 'Creative baseline hash: `{"' not in rendered
    assert "Creative baseline hash: `" + "a" * 64 + "`" in rendered
