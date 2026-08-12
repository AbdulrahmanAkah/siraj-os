"""Regression coverage for the V12 paid-retry identity contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.artifact_provenance_v1 import canonical_sha256
from src.application.paid_operation_gateway import (
    PaidOperationGatewayError,
    PaidOperationRequest,
    _validate_retry_authorization,
)
from src.application.paid_operation_identity_v1 import (
    build_paid_operation_identity,
    provider_payload_sha256,
)
from src.application.siraj_luna_upstream_transport_v6_3 import (
    LunaTransportV63Error,
    _resolve_explicit_paid_retry_v9,
)


EPISODE = "episode-002-adam-temptation-fall-repentance"
STAGE = "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA"
PRIOR = "0caccb03-31b4-4739-90f5-90286d344882"
NEW = "2dee08f3-6a36-44cb-91b1-104f49ddcca4"
EXPECTED_IDENTITY = (
    "ea94f7e5ccbb05c139e050ad527955e3eb2d72541eb90d5c0a03bd3cf12d004d"
)


def _identity(payload: dict[str, object]) -> str:
    input_hash = canonical_sha256({"stage_input": "input"})
    return build_paid_operation_identity(
        episode_id=EPISODE,
        stage=STAGE,
        operation_type="OPENAI_RESPONSES",
        provider="OPENAI",
        model="gpt-5.6-luna",
        provider_contract_version="siraj-provider-contract-v1",
        payload=payload,
        input_artifact_hashes={"stage_input": input_hash},
        operation_nonce=input_hash,
        authorization_mode="EPISODE_MASTER",
    )


def _docs(
    repo: Path,
    *,
    identity: str,
    provider_hash: str,
    prior: str = PRIOR,
    new: str = NEW,
) -> None:
    retry_root = (
        repo
        / "projects"
        / EPISODE
        / "orchestration"
        / "explicit-paid-retry-v9"
    )
    retry_root.mkdir(parents=True)
    auth_rel = (
        "projects/"
        + EPISODE
        + "/orchestration/explicit-paid-retry-v9/semantic-editorial-and-technical-qa-authorization.json"
    )
    plan = {
        "authorization_path": auth_rel,
        "automatic_resubmission": False,
        "automatic_retry": False,
        "canonical_request_identity_sha256": identity,
        "provider_payload_sha256": provider_hash,
        "episode_id": EPISODE,
        "new_attempt_id": new,
        "one_shot": True,
        "prior_attempt_id": prior,
        "reason": "EXPLICIT_TEST_AUTHORIZATION",
        "schema_version": "siraj-explicit-paid-retry-plan-v10",
        "stage": STAGE,
        "status": "AUTHORIZED_ONE_SHOT",
    }
    authorization = {
        "automatic_resubmission": False,
        "automatic_retry": False,
        "canonical_request_identity_sha256": identity,
        "provider_payload_sha256": provider_hash,
        "episode_id": EPISODE,
        "new_attempt_id": new,
        "one_shot": True,
        "prior_attempt_id": prior,
        "reason": "EXPLICIT_TEST_AUTHORIZATION",
        "schema_version": "siraj-explicit-paid-retry-authorization-v10",
        "stage": STAGE,
        "status": "ACTIVE",
    }
    (retry_root / "semantic-editorial-and-technical-qa-plan.json").write_text(
        json.dumps(plan), encoding="utf-8"
    )
    (
        retry_root / "semantic-editorial-and-technical-qa-authorization.json"
    ).write_text(json.dumps(authorization), encoding="utf-8")


def _resolve(repo: Path, payload: dict[str, object]) -> dict[str, object] | None:
    return _resolve_explicit_paid_retry_v9(
        repo,
        EPISODE,
        STAGE,
        payload,
        canonical_request_identity_sha256=_identity(payload),
        provider_payload_sha256_value=provider_payload_sha256(payload),
    )


def _request(
    tmp_path: Path,
    *,
    retry_authorization_reference: dict[str, object] | None,
    prior: str | None = PRIOR,
    attempt: str = NEW,
    payload: dict[str, object] | None = None,
) -> PaidOperationRequest:
    value = payload or {"model": "gpt-5.6-luna", "input": [{"x": 1}]}
    return PaidOperationRequest(
        repo_root=tmp_path,
        episode_id=EPISODE,
        stage=STAGE,
        operation_type="OPENAI_RESPONSES",
        provider="OPENAI",
        model="gpt-5.6-luna",
        provider_contract_version="siraj-provider-contract-v1",
        payload=value,
        input_artifact_hashes={"stage_input": "a" * 64},
        master_authorization_reference={},
        retry_authorization_reference=retry_authorization_reference,
        prior_attempt_id=prior,
        operation_nonce="a" * 64,
        attempt_id=attempt,
    )


def _valid_retry_reference(request: PaidOperationRequest) -> dict[str, object]:
    return {
        "status": "ACTIVE",
        "prior_attempt_id": request.prior_attempt_id,
        "new_attempt_id": request.immutable_attempt_id,
        "canonical_request_identity_sha256": request.canonical_request_identity_sha256,
        "provider_payload_sha256": request.payload_sha256,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "one_shot": True,
        "reason": "EXPLICIT_TEST_AUTHORIZATION",
    }


def test_wrong_semantic_layer_hash_fails_clearly(tmp_path: Path) -> None:
    payload = {"model": "gpt-5.6-luna", "input": [{"x": 1}]}
    wrong_hash = canonical_sha256({"evidence_package": payload})
    _docs(
        tmp_path,
        identity=wrong_hash,
        provider_hash=provider_payload_sha256(payload),
    )
    with pytest.raises(
        LunaTransportV63Error,
        match="EXPLICIT_PAID_RETRY_PLAN_BINDING_INVALID",
    ):
        _resolve(tmp_path, payload)


def test_canonical_paid_request_identity_passes(tmp_path: Path) -> None:
    payload = {"model": "gpt-5.6-luna", "input": [{"x": 1}]}
    _docs(
        tmp_path,
        identity=_identity(payload),
        provider_hash=provider_payload_sha256(payload),
    )
    result = _resolve(tmp_path, payload)
    assert result is not None
    assert result["new_attempt_id"] == NEW
    assert result["prior_attempt_id"] == PRIOR


def test_changing_immutable_paid_request_invalidates_binding(tmp_path: Path) -> None:
    original = {"model": "gpt-5.6-luna", "input": [{"x": 1}]}
    changed = {"model": "gpt-5.6-luna", "input": [{"x": 2}]}
    _docs(
        tmp_path,
        identity=_identity(original),
        provider_hash=provider_payload_sha256(original),
    )
    with pytest.raises(
        LunaTransportV63Error,
        match="EXPLICIT_PAID_RETRY_PLAN_BINDING_INVALID",
    ):
        _resolve(tmp_path, changed)


def test_canonical_json_order_does_not_change_identity() -> None:
    first = {
        "model": "gpt-5.6-luna",
        "input": [{"a": 1, "b": 2}],
    }
    second = {
        "input": [{"b": 2, "a": 1}],
        "model": "gpt-5.6-luna",
    }
    assert provider_payload_sha256(first) == provider_payload_sha256(second)
    assert _identity(first) == _identity(second)


def test_attempt_lineage_is_not_part_of_paid_operation_identity(tmp_path: Path) -> None:
    first = _request(
        tmp_path,
        retry_authorization_reference=None,
        prior=PRIOR,
        attempt=NEW,
    )
    second = _request(
        tmp_path,
        retry_authorization_reference=None,
        prior="another-prior",
        attempt="another-attempt",
    )
    assert first.canonical_request_identity_sha256 == second.canonical_request_identity_sha256
    assert first.immutable_attempt_id != second.immutable_attempt_id


def test_prior_attempt_mismatch_fails() -> None:
    request = _request(
        Path("."),
        retry_authorization_reference=None,
        prior="different-prior",
    )
    reference = _valid_retry_reference(request)
    reference["prior_attempt_id"] = PRIOR
    request = _request(
        Path("."),
        retry_authorization_reference=reference,
        prior="different-prior",
    )
    with pytest.raises(PaidOperationGatewayError, match="prior_attempt_id"):
        _validate_retry_authorization(request)


def test_attempt_id_mismatch_fails(tmp_path: Path) -> None:
    request = _request(tmp_path, retry_authorization_reference=None)
    reference = _valid_retry_reference(request)
    reference["new_attempt_id"] = "different-attempt"
    request = _request(tmp_path, retry_authorization_reference=reference)
    with pytest.raises(PaidOperationGatewayError, match="new_attempt_id"):
        _validate_retry_authorization(request)


@pytest.mark.parametrize("field", ["automatic_retry", "automatic_resubmission"])
def test_automatic_retry_or_resubmission_fails(
    tmp_path: Path,
    field: str,
) -> None:
    request = _request(tmp_path, retry_authorization_reference=None)
    reference = _valid_retry_reference(request)
    reference[field] = True
    request = _request(tmp_path, retry_authorization_reference=reference)
    with pytest.raises(PaidOperationGatewayError, match=field):
        _validate_retry_authorization(request)


def test_consumed_retry_authorization_cannot_start_second_attempt(
    tmp_path: Path,
) -> None:
    payload = {"model": "gpt-5.6-luna", "input": [{"x": 1}]}
    _docs(
        tmp_path,
        identity=_identity(payload),
        provider_hash=provider_payload_sha256(payload),
    )
    events_path = (
        tmp_path
        / "projects"
        / EPISODE
        / "orchestration"
        / "paid-operation-attempts-v1"
        / NEW
        / "attempt-events.jsonl"
    )
    events_path.parent.mkdir(parents=True)
    events_path.write_text(json.dumps({"status": "PLANNED"}) + "\n", encoding="utf-8")
    with pytest.raises(
        LunaTransportV63Error,
        match="AUTHORIZATION_CONSUMED_NEW_HUMAN_AUTH_REQUIRED",
    ):
        _resolve(tmp_path, payload)


def test_unrelated_first_attempt_has_no_retry_interference(tmp_path: Path) -> None:
    payload = {"model": "gpt-5.6-luna", "input": [{"x": 1}]}
    _docs(
        tmp_path,
        identity=_identity(payload),
        provider_hash=provider_payload_sha256(payload),
    )
    assert (
        _resolve_explicit_paid_retry_v9(
            tmp_path,
            EPISODE,
            "OTHER_STAGE",
            payload,
            canonical_request_identity_sha256=_identity(payload),
            provider_payload_sha256_value=provider_payload_sha256(payload),
        )
        is None
    )


def test_certification_records_exact_desktop_safe_boundary() -> None:
    report_path = Path(
        "projects/episode-002-adam-temptation-fall-repentance/orchestration/"
        "ep002-paid-retry-canonical-identity-release-certification-v12-final.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert report["exact_desktop_runtime_gate"] == "PASS"
    assert report["exact_gate_safe_stop_before_network"] is True
    assert report["exact_gate_network_calls"] == 0
    assert report["exact_gate_paid_calls"] == 0
    assert report["canonical_request_identity_sha256"] == EXPECTED_IDENTITY
    assert report["retry_attempt_id"] == NEW
