from __future__ import annotations

import json
from pathlib import Path
import uuid

import pytest

from src.application.artifact_provenance_v1 import (
    artifact_reference,
    canonical_sha256,
    read_jsonl,
    write_new_json,
)
from src.application.desktop_provider_execution_v1 import (
    CanonicalRunwarePaidGateway,
    DesktopProviderExecutionError,
)
from src.application.paid_operation_gateway import (
    PROVIDER_SUBMISSION_INTENT_PERSISTED,
    PaidOperationRequest,
    execute_bytes,
)
from src.application.provider_model_contracts import (
    ProviderModelContractError,
    is_uuid4,
    validate_runware_task,
)


def _master_reference(root: Path) -> dict[str, str]:
    path = root / "master.json"
    value = {
        "status": "ACTIVE",
        "episode_id": "fixture-episode",
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "publishing": "HUMAN_ONLY",
    }
    value["authorization_sha256"] = canonical_sha256(value)
    write_new_json(path, value)
    return artifact_reference(path, base=root)


def _video_payload(task_uuid: str) -> dict[str, object]:
    return {
        "taskType": "videoInference",
        "taskUUID": task_uuid,
        "model": "google:veo@3.1-lite",
        "positivePrompt": "A distinct, approved cinematic motion phase.",
        "width": 1280,
        "height": 720,
        "duration": 4,
        "numberResults": 1,
        "deliveryMethod": "async",
        "includeCost": True,
        "providerSettings": {"google": {"generateAudio": False}},
    }


def _request(root: Path, payload: dict[str, object]) -> PaidOperationRequest:
    return PaidOperationRequest(
        repo_root=root,
        episode_id="fixture-episode",
        stage="FINAL_TTS",
        operation_type="RUNWARE_VIDEO_GENERATION",
        provider="RUNWARE",
        model="google:veo@3.1-lite",
        provider_contract_version="siraj-provider-model-contracts-v1",
        payload=payload,
        input_artifact_hashes={"fixture": "f" * 64},
        master_authorization_reference=_master_reference(root),
        operation_nonce="fixture-video-unit",
    )


def test_uuid4_is_required_only_at_the_paid_runware_boundary() -> None:
    valid = str(uuid.uuid4())
    assert is_uuid4(valid)
    assert validate_runware_task(_video_payload(valid)).payload["taskUUID"] == valid
    assert validate_runware_task(
        _video_payload("planning-only-history-id")
    ).payload["taskUUID"] == "planning-only-history-id"
    with pytest.raises(ProviderModelContractError, match="UUID4_REQUIRED"):
        validate_runware_task(
            _video_payload("planning-only-history-id"),
            require_uuid_v4=True,
        )


def test_uuid_is_part_of_exact_payload_hash() -> None:
    first = _video_payload(str(uuid.uuid4()))
    second = dict(first)
    second["taskUUID"] = str(uuid.uuid4())
    assert canonical_sha256(first) != canonical_sha256(second)


def test_task_uuid_is_durable_before_transport_bytes(tmp_path: Path) -> None:
    task_uuid = str(uuid.uuid4())
    request = _request(tmp_path, _video_payload(task_uuid))
    observed: dict[str, object] = {}

    def transport(boundary):
        request_path = (
            tmp_path
            / "projects"
            / "fixture-episode"
            / "orchestration"
            / "paid-operation-attempts-v1"
            / request.immutable_attempt_id
            / "request.json"
        )
        observed["request"] = json.loads(request_path.read_text(encoding="utf-8-sig"))
        events = read_jsonl(request_path.parent / "attempt-events.jsonl")
        observed["intent"] = any(
            row.get("status") == PROVIDER_SUBMISSION_INTENT_PERSISTED
            for row in events
        )
        boundary("REQUEST_BYTES_HANDED_TO_TRANSPORT", {})
        boundary("RESPONSE_HEADERS_RECEIVED", {"http_status": 200})
        return b"{}"

    result = execute_bytes(request, transport)
    assert result.status == "COMPLETE"
    assert observed["intent"] is True
    request_value = observed["request"]
    assert isinstance(request_value, dict)
    assert request_value["provider_task_uuid"] == task_uuid
    assert request_value["payload"]["taskUUID"] == task_uuid
    assert request_value["payload_sha256"] == canonical_sha256(request_value["payload"])


def test_invalid_planning_identity_is_rejected_before_transport(tmp_path: Path) -> None:
    request = _request(tmp_path, _video_payload("planning-only-23fd9f353315ea244f26e1940c4fe737"))
    calls: list[str] = []

    def transport(_boundary):
        calls.append("transport")
        return b"{}"

    with pytest.raises(ProviderModelContractError, match="UUID4_REQUIRED"):
        execute_bytes(request, transport)
    assert calls == []
    assert not (
        tmp_path
        / "projects"
        / "fixture-episode"
        / "orchestration"
        / "paid-operation-attempts-v1"
        / request.immutable_attempt_id
        / "request.json"
    ).exists()


def test_canonical_runware_gateway_rejects_planning_identity_before_submit(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, _video_payload("planning-only-23fd9f353315ea244f26e1940c4fe737"))
    gateway = CanonicalRunwarePaidGateway()
    with pytest.raises(ProviderModelContractError, match="UUID4_REQUIRED"):
        gateway.submit(
            request=request,
            unit={"media_kind": "RUNWARE_VIDEO", "model": request.model},
            attempt_id=request.immutable_attempt_id,
        )


def test_get_task_details_and_get_response_are_read_only_same_uuid(tmp_path: Path) -> None:
    task_uuid = str(uuid.uuid4())
    calls: list[dict[str, object]] = []

    def lookup(payload: dict[str, object]) -> dict[str, object]:
        calls.append(dict(payload))
        if payload["taskType"] == "getTaskDetails":
            return {"data": [{"taskUUID": task_uuid, "status": "processing"}]}
        return {
            "data": [
                {
                    "taskUUID": task_uuid,
                    "status": "success",
                    "videoURL": "https://example.invalid/original.mp4",
                }
            ]
        }

    gateway = CanonicalRunwarePaidGateway(read_only_transport=lookup)
    details = gateway.get_task_details(
        task_uuid=task_uuid,
        repo_root=tmp_path,
        episode_id="fixture-episode",
        attempt_id="original-attempt",
    )
    response = gateway.get_response(
        task_uuid=task_uuid,
        repo_root=tmp_path,
        episode_id="fixture-episode",
        attempt_id="original-attempt",
    )
    assert details["data"][0]["status"] == "processing"
    assert response["data"][0]["status"] == "success"
    assert [row["taskType"] for row in calls] == ["getTaskDetails", "getResponse"]
    assert all("videoInference" != row["taskType"] for row in calls)
    evidence_dir = (
        tmp_path
        / "projects"
        / "fixture-episode"
        / "orchestration"
        / "paid-operation-attempts-v1"
        / "original-attempt"
        / "runware-read-only-reconciliation-v1"
    )
    assert len(list(evidence_dir.glob("*.json"))) == 2
    assert len(list(evidence_dir.glob("*.json.raw"))) == 2


def test_invalid_original_identity_cannot_trigger_read_only_lookup() -> None:
    calls: list[dict[str, object]] = []
    gateway = CanonicalRunwarePaidGateway(read_only_transport=lambda payload: calls.append(payload) or {})
    with pytest.raises(DesktopProviderExecutionError, match="UUID4_REQUIRED_FOR_LOOKUP"):
        gateway.get_task_details(task_uuid="planning-only-23fd9f353315ea244f26e1940c4fe737")
    assert calls == []


def test_reconciliation_rejects_a_different_task_uuid(tmp_path: Path) -> None:
    original = str(uuid.uuid4())
    request = _request(tmp_path, _video_payload(original))
    gateway = CanonicalRunwarePaidGateway(read_only_transport=lambda _payload: {})
    with pytest.raises(DesktopProviderExecutionError, match="BINDING_MISMATCH"):
        gateway.reconcile_submitted_operation(
            request=request,
            unit={"media_kind": "RUNWARE_VIDEO"},
            attempt_id=request.immutable_attempt_id,
            provider_operation_id=str(uuid.uuid4()),
            max_polls=1,
        )
