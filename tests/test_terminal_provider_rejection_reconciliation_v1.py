from __future__ import annotations

import dataclasses
import json
import shutil
import socket
from pathlib import Path

import pytest

from src.application.artifact_provenance_v1 import read_jsonl, sha256_file
from src.application.desktop_media_cost_preflight_v1 import (
    read_persisted_media_cost_preflight,
)
from src.application.desktop_provider_execution_v1 import (
    CanonicalDesktopProviderExecutionExecutor,
    _siraj_provider_execution_recovery_session_v2,
)
from src.application.provider_attempt_reconciliation_v1 import (
    PROVEN_NOT_CHARGED,
    PROVEN_SUBMITTED_TERMINAL_REJECTED,
    TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED,
    append_terminal_provider_rejection_reconciliation,
    reconciliation_for_attempt,
    reconciliation_for_request,
)

REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"
UNIT = "EP002-SH-022-V02"
SHOT = "EP002-SH-022"
ATTEMPT = "8b90dd6e-570e-59c6-8e89-bcb5fddb5a12"
POLL = "777373e8-b0d4-517e-be4f-e84a0f8d5bc1"
TASK_UUID = "9a6e7ed8-406a-4623-8f26-bf048ed0943d"
ERROR_SHA = "cbb7f5d1a69d2e023e166f9ec892abd8b9327a0952420504488e1b42a5313d64"

BINDING_KEYS = {
    "episode_id",
    "stage",
    "preflight_file_sha256",
    "preflight_payload_sha256",
    "media_plan_sha256",
    "provider_request_plan_sha256",
    "pricing_registry_sha256",
    "pricing_registry_version",
    "reack_receipt_id",
    "maximum_cost",
    "currency",
    "ledger_head_sha256",
    "creative_overlay_sha256",
    "structural_fingerprint",
    "request_plan_hash",
}


def _copy(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _clone(tmp_path: Path) -> Path:
    root = tmp_path / "terminal-provider-rejection-clone"
    _copy(REPO / "projects" / EPISODE, root / "projects" / EPISODE)
    for rel in ("projects/_series", "projects/_orchestrator"):
        _copy(REPO / rel, root / rel)
    # SIRAJ_TEST_STRIP_LIVE_REPLACEMENT_AUTH_V1
    auth = (
        root
        / "projects"
        / EPISODE
        / "orchestration"
        / "provider-execution-v1"
        / "terminal-provider-replacement-authorization-v1.json"
    )
    if auth.is_file():
        auth.unlink()
    consumption = auth.with_name(
        "terminal-provider-replacement-consumption-v1.jsonl"
    )
    if consumption.is_file():
        consumption.unlink()
    return root


def _deny_network(*args, **kwargs):
    raise AssertionError("NETWORK_FORBIDDEN_IN_TERMINAL_RECONCILIATION_TEST")


def _binding(root: Path) -> dict:
    executor = CanonicalDesktopProviderExecutionExecutor(root, EPISODE)
    review = read_persisted_media_cost_preflight(root, EPISODE)
    value = executor._binding(review)
    if hasattr(value, "as_dict"):
        raw = value.as_dict()
    elif dataclasses.is_dataclass(value):
        raw = dataclasses.asdict(value)
    else:
        raw = dict(value)
    return {key: raw[key] for key in BINDING_KEYS if key in raw}


def _target_unit(root: Path) -> dict:
    value = json.loads(
        (
            root
            / "projects"
            / EPISODE
            / "orchestration"
            / "media-cost-preflight-v2.json"
        ).read_text(encoding="utf-8-sig")
    )
    return next(row for row in value["units"] if row["unit_id"] == UNIT)


def _append(root: Path):
    unit = _target_unit(root)
    return append_terminal_provider_rejection_reconciliation(
        root,
        EPISODE,
        historical_attempt_id=ATTEMPT,
        provider_request_id=UNIT,
        shot_id=SHOT,
        media_unit_id=UNIT,
        provider="RUNWARE",
        model="google:veo@3.1-lite",
        media_type=str(unit.get("media_kind") or "RUNWARE_VIDEO"),
        planned_cost_usd=float(unit["expected_cost_usd"]),
        provider_operation_id=TASK_UUID,
        failed_poll_attempt_id=POLL,
        provider_error_code="invalidProviderContent",
        provider_error_response_path=(
            "projects/" + EPISODE
            + "/orchestration/paid-operation-attempts-v1/"
            + POLL + "/http-error-response.bin"
        ),
        provider_error_response_sha256=ERROR_SHA,
        binding=_binding(root),
    )


def test_live_failure_clone_reconciles_append_only_and_stays_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    root = _clone(tmp_path)

    execution_ledger = (
        root / "projects" / EPISODE / "orchestration"
        / "provider-execution-v1"
        / "provider-execution-attempt-receipts-v1.jsonl"
    )
    historical_hash = sha256_file(execution_ledger)

    receipt = _append(root)
    assert receipt["original_submission_status"] == PROVEN_SUBMITTED_TERMINAL_REJECTED
    assert receipt["original_charge_status"] == PROVEN_NOT_CHARGED
    assert receipt["request_status"] == TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED
    assert receipt["terminal_provider_rejection"] is True
    assert receipt["safe_to_reauthorize"] is True
    assert receipt["explicit_no_charge_statement"] is True
    assert receipt["billable_output_detected"] is False
    assert receipt["replacement_authorized"] is False
    assert receipt["attempt_ordinal_consumed"] is True
    assert receipt["automatic_paid_retry"] is False
    assert receipt["automatic_paid_resubmission"] is False
    assert sha256_file(execution_ledger) == historical_hash

    by_attempt = reconciliation_for_attempt(root, EPISODE, ATTEMPT)
    by_request = reconciliation_for_request(root, EPISODE, UNIT)
    assert by_attempt is not None and by_request is not None
    assert by_attempt["receipt_id"] == receipt["receipt_id"]
    assert by_request["receipt_id"] == receipt["receipt_id"]

    executor = CanonicalDesktopProviderExecutionExecutor(root, EPISODE)
    state = executor.reconcile()
    assert state["request_states"][UNIT] == TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED
    assert UNIT in state["blocked_requests"]
    assert UNIT in state["terminal_rejection_reauthorization_required"]
    assert UNIT not in state["not_submitted_requests_eligible"]
    assert _siraj_provider_execution_recovery_session_v2(
        root, EPISODE, state
    ) is None


def test_exact_durable_append_is_idempotent(tmp_path: Path) -> None:
    root = _clone(tmp_path)
    first = _append(root)
    second = _append(root)
    assert first["receipt_id"] == second["receipt_id"]
    ledger = (
        root / "projects" / EPISODE / "orchestration"
        / "provider-attempt-reconciliation-v1.jsonl"
    )
    rows = [
        row for row in read_jsonl(ledger)
        if row.get("historical_attempt_id") == ATTEMPT
    ]
    assert len(rows) == 1


def test_wrong_provider_operation_fails_closed(tmp_path: Path) -> None:
    root = _clone(tmp_path)
    unit = _target_unit(root)
    with pytest.raises(Exception):
        append_terminal_provider_rejection_reconciliation(
            root,
            EPISODE,
            historical_attempt_id=ATTEMPT,
            provider_request_id=UNIT,
            shot_id=SHOT,
            media_unit_id=UNIT,
            provider="RUNWARE",
            model="google:veo@3.1-lite",
            media_type=str(unit.get("media_kind") or "RUNWARE_VIDEO"),
            planned_cost_usd=float(unit["expected_cost_usd"]),
            provider_operation_id="11111111-1111-4111-8111-111111111111",
            failed_poll_attempt_id=POLL,
            provider_error_code="invalidProviderContent",
            provider_error_response_path=(
                "projects/" + EPISODE
                + "/orchestration/paid-operation-attempts-v1/"
                + POLL + "/http-error-response.bin"
            ),
            provider_error_response_sha256=ERROR_SHA,
            binding=_binding(root),
        )
