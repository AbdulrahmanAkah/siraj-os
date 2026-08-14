from __future__ import annotations

from decimal import Decimal
from dataclasses import replace
from pathlib import Path

import pytest

from src.application.pr01_production_readiness_v1 import (
    BindingMismatchError,
    CONSTITUTION_BUNDLE_SHA256,
    CONSTITUTION_VERSION,
    EXACT_MODEL_ID,
    PaidStartDenied,
    PaidStartCard,
    build_exact_provider_payload,
    canonical_sha256,
    classify_audio_measurement,
    cost_preflight,
    evaluate_paid_start,
    historical_unknown_state,
    load_pricing_snapshot,
    load_profile,
    rebind_pr01_constitution_binding,
    validate_exact_provider_payload,
    validate_profile,
)
from src.application.desktop_provider_execution_v1 import CanonicalRunwarePaidGateway
from src.application.paid_operation_gateway import PaidOperationRequest


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_profile_is_single_authority_and_face_policy_is_fail_closed() -> None:
    profile = load_profile(REPO_ROOT)
    assert validate_profile(profile) == []
    assert profile["constitution_binding"]["constitution_version"] == CONSTITUTION_VERSION
    assert profile["constitution_binding"]["constitution_bundle_sha256"] == CONSTITUTION_BUNDLE_SHA256
    assert profile["face_policy"]["all_human_faces_visible"] is False
    assert profile["publication_policy"]["human_final_certification_required"] is True


def test_constitution_amendment_invalidates_and_rebinds_pr01_without_authorization() -> None:
    result = rebind_pr01_constitution_binding(REPO_ROOT)
    assert result["status"] == "PASS"
    assert result["invalidation_event"] == "constitution_bundle_changed"
    assert result["prior_approvals"] == "INVALIDATED"
    assert result["m01_m02_m03_rebuild_required"] is False
    assert result["m01_m02_m03_compatibility_revalidated"] is True
    assert result["historical_unknown"]["status"] == "UNKNOWN_REMAINS_BLOCK"
    assert result["historical_unknown"]["retry_allowed"] is False
    assert result["historical_unknown"]["resubmission_allowed"] is False
    assert result["production_authorized"] is False
    assert result["paid_execution_authorized"] is False


def test_exact_provider_binding_rejects_alias_and_negative_prompt() -> None:
    payload = build_exact_provider_payload(
        prompt="Abstract earth surface with no figures.",
        duration_seconds=4,
        task_uuid="00000000-0000-4000-8000-000000000001",
    )
    assert payload["model"] == EXACT_MODEL_ID
    assert validate_exact_provider_payload(payload)["model"] == EXACT_MODEL_ID
    alias = dict(payload)
    alias["model"] = "google:veo@3.1"
    with pytest.raises(BindingMismatchError, match="EXACT_MODEL_ID_REQUIRED"):
        validate_exact_provider_payload(alias)
    negative = dict(payload)
    negative["negativePrompt"] = "anything"
    with pytest.raises(BindingMismatchError, match="UNBOUND_PROVIDER_PAYLOAD_FIELDS"):
        validate_exact_provider_payload(negative)


def test_global_face_semantics_rejects_legacy_positive_phrase() -> None:
    with pytest.raises(BindingMismatchError, match="FAIL_GLOBAL_FACE_POLICY"):
        build_exact_provider_payload(
            prompt="A stable face with a visible mouth.",
            duration_seconds=4,
            task_uuid="00000000-0000-4000-8000-000000000001",
        )


def test_decimal_cost_preflight_is_hash_bound() -> None:
    pricing = load_pricing_snapshot(REPO_ROOT)
    result = cost_preflight(
        [{"unit_id": "u1", "duration_seconds": 8, "resolution": "720p"}],
        pricing,
        max_cost_usd=Decimal("1.00"),
    )
    assert result["estimated_cost_usd"] == "0.40"
    assert result["decimal_arithmetic"] is True
    assert result["pricing_snapshot_hash"]


def test_audio_unknown_cannot_pass() -> None:
    profile = load_profile(REPO_ROOT)
    assert classify_audio_measurement({"status": "UNKNOWN"}, profile)["status"] == "BLOCKED"


def test_paid_start_is_desktop_click_only_and_stales_on_changed_card() -> None:
    card = PaidStartCard(
        episode_id="EP002",
        provider="RUNWARE",
        exact_model_id=EXACT_MODEL_ID,
        request_count=1,
        provider_seconds=4,
        estimated_cost_usd="0.20",
        maximum_cost_usd="1.00",
        currency="USD",
        batch_type="PILOT",
        prompt_hashes=(canonical_sha256("prompt"),),
        payload_hashes=(canonical_sha256({"payload": 1}),),
        pricing_snapshot_hash="pricing",
        provider_binding_hash="binding",
        technical_profile_hash="profile",
        compatibility_transform_hash="transform",
    )
    blocked = evaluate_paid_start(
        card,
        origin="CLI",
        explicit_click=True,
        human_approval=True,
        click_nonce="n1",
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["production_authorized"] is False
    stale = evaluate_paid_start(
        card,
        origin="DESKTOP",
        explicit_click=True,
        human_approval=True,
        click_nonce="n1",
        current_card=replace(card, estimated_cost_usd="0.21"),
    )
    assert "APPROVAL_STALE_INPUT_CHANGED" in stale["reasons"]


def test_unknown_state_is_immutable_and_never_retried() -> None:
    state = historical_unknown_state()
    assert state["attempt_id"] == "1e6d0013-d37f-5df7-ab53-444c4f17c14c"
    assert state["retry_allowed"] is False
    assert state["resubmission_allowed"] is False
    assert state["status"] == "UNKNOWN_REMAINS_BLOCK"


def test_real_gateway_blocks_before_transport_without_pr01_desktop_card(tmp_path: Path) -> None:
    payload = build_exact_provider_payload(
        prompt="Abstract earth surface with no figures.",
        duration_seconds=4,
        task_uuid="00000000-0000-4000-8000-000000000001",
    )
    request = PaidOperationRequest(
        repo_root=tmp_path,
        episode_id="fixture",
        stage="PROVIDER_EXECUTION",
        operation_type="RUNWARE_VIDEO",
        provider="RUNWARE",
        model=EXACT_MODEL_ID,
        provider_contract_version="test",
        payload=payload,
        input_artifact_hashes={},
        master_authorization_reference={},
    )
    with pytest.raises(PaidStartDenied, match="PR01_DESKTOP_APPROVAL_REQUIRED"):
        CanonicalRunwarePaidGateway().submit(
            request=request,
            unit={"unit_id": "fixture", "model": EXACT_MODEL_ID, "media_kind": "RUNWARE_VIDEO"},
            attempt_id="fixture-attempt",
        )
