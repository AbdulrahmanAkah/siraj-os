from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from src.application.artifact_provenance_v1 import (
    artifact_reference,
    canonical_sha256,
    write_new_json,
)
from src.application.controlled_alignment_validation_v1 import (
    offline_control_mode_proof,
)
from src.application.paid_operation_gateway import (
    CONTROLLED_ALIGNMENT_AUTHORIZATION_SCHEMA,
    PaidOperationGatewayError,
    PaidOperationRequest,
    execute_json,
)


def _request(root: Path, authorization_reference, attempt_id: str) -> PaidOperationRequest:
    return PaidOperationRequest(
        repo_root=root,
        episode_id="fixture-episode",
        stage="NARRATION_VISUAL_ALIGNMENT_GATE",
        operation_type="OPENAI_RESPONSES",
        provider="OPENAI",
        model="gpt-5.6-luna",
        provider_contract_version="test-v1",
        payload={"model": "gpt-5.6-luna", "store": False, "input": ["fixture"]},
        input_artifact_hashes={"fixture": "f" * 64},
        master_authorization_reference=authorization_reference,
        authorization_mode="CONTROLLED_ALIGNMENT_VALIDATION",
        operation_nonce="controlled-fixture",
        attempt_id=attempt_id,
    )


def _authorization(root: Path, request: PaidOperationRequest):
    path = root / "controlled-authorization.json"
    value = {
        "schema_version": CONTROLLED_ALIGNMENT_AUTHORIZATION_SCHEMA,
        "status": "ACTIVE",
        "episode_id": request.episode_id,
        "scope": "CONTROLLED_ALIGNMENT_VALIDATION_ONLY",
        "allowed_stage": request.stage,
        "allowed_provider": request.provider,
        "allowed_model": request.model,
        "allowed_operation_type": request.operation_type,
        "maximum_real_luna_attempts": 1,
        "planned_attempt_id": request.immutable_attempt_id,
        "payload_sha256": request.payload_sha256,
        "request_identity_sha256": request.request_identity_sha256,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "authorizes_downstream_continuation": False,
        "authorizes_paid_retry": False,
        "authorizes_media_generation": False,
    }
    value["authorization_sha256"] = canonical_sha256(value)
    write_new_json(path, value)
    return artifact_reference(path, base=root)


def test_controlled_authorization_is_bound_to_one_planned_attempt(tmp_path: Path):
    provisional = _request(tmp_path, {}, str(uuid.uuid4()))
    authorization = _authorization(tmp_path, provisional)
    request = _request(tmp_path, authorization, provisional.immutable_attempt_id)
    calls = []

    def transport(boundary):
        calls.append("transport")
        boundary("REQUEST_BYTES_HANDED_TO_TRANSPORT", {})
        boundary("RESPONSE_HEADERS_RECEIVED", {"http_status": 200})
        return b"{}"

    result, payload = execute_json(request, transport)
    assert result.status == "COMPLETE"
    assert payload == {}
    assert calls == ["transport"]

    second = _request(tmp_path, authorization, str(uuid.uuid4()))
    with pytest.raises(PaidOperationGatewayError, match="CONTROLLED_ALIGNMENT_AUTHORIZATION_BINDING_INVALID"):
        execute_json(second, transport)
    assert calls == ["transport"]


def test_offline_control_mode_proof_uses_one_fake_proposal_only():
    result = offline_control_mode_proof(
        Path(__file__).resolve().parents[1],
        "episode-002-adam-temptation-fall-repentance",
    )
    assert result["status"] == "PASS"
    assert result["paid_attempt_count_simulated"] == 1
    assert result["second_luna_attempt_blocked"] is True
    assert result["downstream_stage_execution"] == 0
    assert result["runware_calls"] == result["veo_calls"] == result["elevenlabs_calls"] == 0
    assert result["automatic_retry"] is False
