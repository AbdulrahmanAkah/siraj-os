from __future__ import annotations

import json
import hashlib
from pathlib import Path

from src.application.provider_model_contracts import validate_runware_task


ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "reports/episode-002-media-planner-v2-contract-valid-proposal.json"
MIGRATION = ROOT / "reports/episode-002-media-planner-v2-preflight-migration-proposal.json"
REGISTRY = ROOT / "projects/_series/siraj-media-pricing-registry-v2.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_contract_valid_proposal_reselects_all_invalid_durations() -> None:
    proposal = _load(PROPOSAL)
    assert proposal["provider_contracts"]["status"] == "PASS"
    assert len(proposal["video_units"]) == 73
    assert len(proposal["invalid_preserved_video_units"]) == 25
    assert all(unit["selected_provider_duration"] in {4, 6, 8} for unit in proposal["video_units"])
    assert all(unit["contract_status"] == "PASS" for unit in proposal["video_units"])
    assert all(unit["minimum_usable_generation_seconds"] >= unit["timeline_required_seconds"] for unit in proposal["video_units"])
    assert all(unit["provider_request_contract"]["negative_prompt_field_present"] is False for unit in proposal["video_units"])


def test_contract_valid_proposal_preserves_coverage_and_static_sequence() -> None:
    proposal = _load(PROPOSAL)
    assert proposal["authoritative_inputs"]["structural_fingerprint"] == "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
    assert proposal["authoritative_inputs"]["compatibility_provider_plan_structural_fingerprint"] == "7f35e6d534c57454087ab54d70b4cea51cc3669e75d573709846ae2240ed4a43"
    coverage = proposal["coverage"]
    assert coverage["true_generated_video_timeline_seconds"] == 428.56
    assert coverage["true_generated_video_timeline_percent"] == 68.725304
    assert coverage["coverage_validation"]["status"] == "PASS"
    assert coverage["longest_no_true_video_span_seconds"] == 56.021
    assert proposal["static_sequence_policy"]["classification"] == "ACCEPTABLE_MIXED_STATIC_SEQUENCE"
    assert proposal["static_sequence_policy"]["preserved"] is True
    assert proposal["quality_constraints"]["structural_change"] == "NONE"


def test_current_pricing_binding_and_cost_are_complete() -> None:
    proposal = _load(PROPOSAL)
    registry_hash = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    assert proposal["pricing_binding"]["status"] == "VALID"
    assert proposal["pricing_binding"]["pricing_registry_sha256"] == registry_hash
    assert proposal["cost_summary"]["pricing_status"] == "COMPLETE"
    assert proposal["cost_summary"]["priced_requests"] == 95
    assert proposal["cost_summary"]["unpriced_requests"] == 0
    assert proposal["cost_summary"]["estimated_total_cost_usd"] == 25.9009
    assert proposal["pricing_contract_consistency"] == "PASS"


def test_low_utilization_is_explicit_provider_minimum_overhead() -> None:
    proposal = _load(PROPOSAL)
    units = proposal["low_utilization_units"]
    assert len([row for row in units if row["utilization_percent"] < 75]) == 18
    assert len([row for row in units if row["utilization_percent"] < 50]) == 14
    assert len([row for row in units if row["utilization_percent"] < 25]) == 8
    assert all("smallest supported Veo unit" in row["reason"] for row in units)


def test_migration_is_proposal_only_and_does_not_authorize_spend() -> None:
    migration = _load(MIGRATION)
    assert migration["status"] == "PROPOSED_NOT_APPROVED_NOT_APPLIED"
    assert migration["authorizes_paid_operation"] is False
    assert migration["authorizes_resume"] is False
    assert migration["human_migration_approval_required"] is True
    assert migration["safety"]["provider_api_calls"] == 0
    assert migration["safety"]["paid_provider_calls"] == 0
    assert migration["safety"]["ledger_mutated"] is False
    assert migration["safety"]["authorization_mutated"] is False


def test_veo_request_schema_is_contract_valid_and_negative_prompt_free() -> None:
    proposal = _load(PROPOSAL)
    for unit in proposal["video_units"]:
        contract = unit["provider_request_contract"]
        assert contract["duration"] in {4, 6, 8}
        assert contract["negative_prompt_field_present"] is False
        payload = {
            "taskType": "videoInference",
            "taskUUID": unit["planning_identity"],
            "model": contract["model"],
            "positivePrompt": "planning-only validation",
            "width": contract["width"],
            "height": contract["height"],
            "duration": contract["duration"],
            "numberResults": contract["number_results"],
            "deliveryMethod": "async",
            "includeCost": True,
            "providerSettings": {"google": {"generateAudio": False}},
        }
        validated = validate_runware_task(payload)
        assert validated.provider == "RUNWARE"
        assert validated.model == "google:veo@3.1-lite"
