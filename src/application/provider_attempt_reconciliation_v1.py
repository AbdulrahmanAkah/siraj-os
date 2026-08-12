"""Append-only reconciliation of provider-attempt evidence.

This module is deliberately separate from the paid-attempt ledger.  A human
provider-account review can establish that an ambiguous attempt was never
created by the provider, but it must not rewrite the original UNKNOWN rows or
silently turn the operation into a retry.  The receipt below is therefore an
immutable, hash-addressed correction which makes the request eligible for a
new *first* submission only when the future Desktop executor is explicitly
resumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import json
import uuid

from src.application.artifact_provenance_v1 import (
    _THREAD_LOCK,
    _fsync_directory,
    _process_lock,
    canonical_json_bytes,
    canonical_sha256,
    read_jsonl,
    sha256_file,
    utc_now,
)
from src.application.episode_transition_ledger_v1 import ledger_path


SCHEMA_VERSION = "siraj-provider-attempt-reconciliation-v1"
RECONCILIATION_LEDGER = "provider-attempt-reconciliation-v1.jsonl"
HUMAN_PROVIDER_ACCOUNT_REVIEW = "HUMAN_PROVIDER_ACCOUNT_REVIEW"
PROVEN_NOT_SUBMITTED = "PROVEN_NOT_SUBMITTED"
PROVEN_NOT_CHARGED = "PROVEN_NOT_CHARGED"
# SIRAJ_TERMINAL_PROVIDER_REJECTION_RECONCILIATION_V1
DURABLE_PROVIDER_TERMINAL_REJECTION = "DURABLE_PROVIDER_TERMINAL_REJECTION"
PROVEN_SUBMITTED_TERMINAL_REJECTED = "PROVEN_SUBMITTED_TERMINAL_REJECTED"
TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED = (
    "TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED"
)
NOT_SUBMITTED_ELIGIBLE = "NOT_SUBMITTED_ELIGIBLE_FOR_FIRST_VALID_SUBMISSION"


class ProviderAttemptReconciliationError(RuntimeError):
    """Fail-closed reconciliation evidence error."""


def reconciliation_ledger_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / RECONCILIATION_LEDGER
    )


def _unsigned(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "receipt_sha256"}


def _valid_row(row: Mapping[str, Any], *, episode_id: str) -> bool:
    return (
        row.get("schema_version") == SCHEMA_VERSION
        and row.get("episode_id") == episode_id
        and row.get("receipt_sha256") == canonical_sha256(_unsigned(row))
        and row.get("evidence_source")
        in {
            HUMAN_PROVIDER_ACCOUNT_REVIEW,
            DURABLE_PROVIDER_TERMINAL_REJECTION,
        }
    )


def read_reconciliation_receipts(
    repo_root: Path,
    episode_id: str,
) -> list[dict[str, Any]]:
    path = reconciliation_ledger_path(repo_root, episode_id)
    try:
        rows = read_jsonl(path)
    except Exception as exc:  # pragma: no cover - defensive corruption guard
        raise ProviderAttemptReconciliationError(
            "PROVIDER_RECONCILIATION_LEDGER_CORRUPT"
        ) from exc
    if any(not _valid_row(row, episode_id=episode_id) for row in rows):
        raise ProviderAttemptReconciliationError(
            "PROVIDER_RECONCILIATION_RECEIPT_INVALID"
        )
    return rows


def _is_current_binding(
    repo_root: Path,
    episode_id: str,
    row: Mapping[str, Any],
) -> bool:
    """Reject copied/stale evidence instead of projecting it into state."""

    ledger = ledger_path(Path(repo_root).resolve(), episode_id)
    bound = str((row.get("binding") or {}).get("ledger_head_sha256") or "")
    return bool(ledger.is_file() and bound and bound == sha256_file(ledger))


def current_reconciliation_receipts(
    repo_root: Path,
    episode_id: str,
) -> list[dict[str, Any]]:
    return [
        row
        for row in read_reconciliation_receipts(repo_root, episode_id)
        if _is_current_binding(repo_root, episode_id, row)
    ]


def reconciliation_for_attempt(
    repo_root: Path,
    episode_id: str,
    attempt_id: str,
) -> dict[str, Any] | None:
    rows = current_reconciliation_receipts(repo_root, episode_id)
    for row in reversed(rows):
        if str(row.get("historical_attempt_id") or "") == attempt_id:
            return row
    return None


def reconciliation_for_request(
    repo_root: Path,
    episode_id: str,
    request_id: str,
) -> dict[str, Any] | None:
    rows = current_reconciliation_receipts(repo_root, episode_id)
    for row in reversed(rows):
        if str(row.get("provider_request_id") or "") == request_id:
            return row
    return None


def append_terminal_provider_rejection_reconciliation(
    repo_root: Path,
    episode_id: str,
    *,
    historical_attempt_id: str,
    provider_request_id: str,
    shot_id: str,
    media_unit_id: str,
    provider: str,
    model: str,
    media_type: str,
    planned_cost_usd: float,
    provider_operation_id: str,
    failed_poll_attempt_id: str,
    provider_error_code: str,
    provider_error_response_path: str,
    provider_error_response_sha256: str,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    # Durable submitted -> terminal-rejected reconciliation.
    # This function does NOT authorize a replacement request.
    required = {
        "historical_attempt_id": historical_attempt_id,
        "provider_request_id": provider_request_id,
        "provider_operation_id": provider_operation_id,
        "failed_poll_attempt_id": failed_poll_attempt_id,
        "provider_error_code": provider_error_code,
        "provider_error_response_path": provider_error_response_path,
        "provider_error_response_sha256": provider_error_response_sha256,
    }
    for label, raw in required.items():
        if not str(raw or "").strip():
            raise ProviderAttemptReconciliationError(
                "TERMINAL_REJECTION_" + label.upper() + "_REQUIRED"
            )
    if not isinstance(binding, Mapping) or not binding:
        raise ProviderAttemptReconciliationError("RECONCILIATION_BINDING_REQUIRED")

    try:
        planned_cost = float(planned_cost_usd)
    except (TypeError, ValueError) as exc:
        raise ProviderAttemptReconciliationError("PLANNED_COST_INVALID") from exc
    if planned_cost < 0:
        raise ProviderAttemptReconciliationError("PLANNED_COST_NEGATIVE")

    repo = Path(repo_root).resolve()
    ledger = ledger_path(repo, episode_id)
    if not ledger.is_file():
        raise ProviderAttemptReconciliationError("AUTHORITATIVE_LEDGER_MISSING")
    current_ledger_head = sha256_file(ledger)
    bound_ledger_head = str(binding.get("ledger_head_sha256") or "")
    if not bound_ledger_head or bound_ledger_head != current_ledger_head:
        raise ProviderAttemptReconciliationError("STALE_RECONCILIATION_BINDING")

    evidence_path = Path(provider_error_response_path)
    if not evidence_path.is_absolute():
        evidence_path = repo / evidence_path
    evidence_path = evidence_path.resolve()
    try:
        evidence_path.relative_to(repo)
    except ValueError as exc:
        raise ProviderAttemptReconciliationError(
            "PROVIDER_ERROR_EVIDENCE_OUTSIDE_REPOSITORY"
        ) from exc
    if evidence_path.parent.name != failed_poll_attempt_id:
        raise ProviderAttemptReconciliationError(
            "FAILED_POLL_EVIDENCE_PATH_BINDING_MISMATCH"
        )
    if not evidence_path.is_file():
        raise ProviderAttemptReconciliationError("PROVIDER_ERROR_EVIDENCE_MISSING")
    evidence_sha = sha256_file(evidence_path)
    if evidence_sha != str(provider_error_response_sha256):
        raise ProviderAttemptReconciliationError(
            "PROVIDER_ERROR_EVIDENCE_HASH_MISMATCH"
        )

    try:
        evidence = json.loads(evidence_path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderAttemptReconciliationError(
            "PROVIDER_ERROR_EVIDENCE_INVALID_JSON"
        ) from exc
    if not isinstance(evidence, Mapping):
        raise ProviderAttemptReconciliationError(
            "PROVIDER_ERROR_EVIDENCE_OBJECT_REQUIRED"
        )
    if evidence.get("data") != []:
        raise ProviderAttemptReconciliationError(
            "TERMINAL_REJECTION_BILLABLE_OUTPUT_NOT_PROVEN_ABSENT"
        )

    errors = evidence.get("errors")
    if not isinstance(errors, list) or not errors:
        raise ProviderAttemptReconciliationError(
            "TERMINAL_REJECTION_PROVIDER_ERROR_REQUIRED"
        )
    matched_error = None
    for candidate in errors:
        if not isinstance(candidate, Mapping):
            continue
        if (
            str(candidate.get("code") or "") == str(provider_error_code)
            and str(candidate.get("taskUUID") or "") == str(provider_operation_id)
            and str(candidate.get("status") or "").lower() == "error"
        ):
            matched_error = candidate
            break
    if matched_error is None:
        raise ProviderAttemptReconciliationError(
            "TERMINAL_REJECTION_PROVIDER_EVIDENCE_BINDING_MISMATCH"
        )

    evidence_text = json.dumps(evidence, ensure_ascii=False, sort_keys=True).lower()
    if "will not be charged" not in evidence_text:
        raise ProviderAttemptReconciliationError(
            "TERMINAL_REJECTION_EXPLICIT_NO_CHARGE_NOT_PROVEN"
        )

    poll_root = evidence_path.parent
    poll_events_path = poll_root / "attempt-events.jsonl"
    poll_request_path = poll_root / "request.json"
    if not poll_events_path.is_file() or not poll_request_path.is_file():
        raise ProviderAttemptReconciliationError("FAILED_POLL_DURABLE_CONTEXT_MISSING")

    poll_events = read_jsonl(poll_events_path)
    poll_failure_proven = any(
        str(row.get("status") or "") == "FAILED"
        and isinstance(row.get("details"), Mapping)
        and int((row.get("details") or {}).get("http_status") or 0) == 400
        and str((row.get("details") or {}).get("error_response_sha256") or "")
        == evidence_sha
        for row in poll_events
    )
    if not poll_failure_proven:
        raise ProviderAttemptReconciliationError(
            "FAILED_POLL_HTTP400_HASH_BINDING_NOT_PROVEN"
        )

    try:
        poll_request = json.loads(poll_request_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderAttemptReconciliationError("FAILED_POLL_REQUEST_INVALID") from exc
    if not isinstance(poll_request, Mapping):
        raise ProviderAttemptReconciliationError(
            "FAILED_POLL_REQUEST_OBJECT_REQUIRED"
        )

    parent_from_poll = str(
        (poll_request.get("input_artifact_hashes") or {}).get("provider_attempt_id")
        or ""
    )
    task_from_poll = str(
        poll_request.get("provider_task_uuid")
        or (poll_request.get("payload") or {}).get("taskUUID")
        or ""
    )
    if parent_from_poll != historical_attempt_id:
        raise ProviderAttemptReconciliationError(
            "FAILED_POLL_PARENT_ATTEMPT_BINDING_MISMATCH"
        )
    if task_from_poll != provider_operation_id:
        raise ProviderAttemptReconciliationError(
            "FAILED_POLL_PROVIDER_OPERATION_BINDING_MISMATCH"
        )

    execution_root = (
        repo
        / "projects"
        / episode_id
        / "orchestration"
        / "provider-execution-v1"
    )
    attempt_ledger = execution_root / "provider-execution-attempt-receipts-v1.jsonl"
    attempt_rows = [
        row
        for row in read_jsonl(attempt_ledger)
        if str(row.get("attempt_id") or "") == historical_attempt_id
    ]
    if not attempt_rows:
        raise ProviderAttemptReconciliationError(
            "HISTORICAL_PROVIDER_ATTEMPT_RECEIPTS_MISSING"
        )

    submitted = any(
        str(row.get("status") or "") == "SUBMITTED_PENDING"
        and str(row.get("provider_operation_id") or "") == provider_operation_id
        and str(
            row.get("provider_request_id")
            or row.get("request_id")
            or row.get("unit_id")
            or ""
        ) == provider_request_id
        for row in attempt_rows
    )
    failed = any(
        str(row.get("status") or "") == "FAILED"
        and str(row.get("unit_id") or "") == media_unit_id
        for row in attempt_rows
    )
    if not submitted:
        raise ProviderAttemptReconciliationError("HISTORICAL_SUBMISSION_NOT_PROVEN")
    if not failed:
        raise ProviderAttemptReconciliationError(
            "HISTORICAL_TERMINAL_FAILURE_NOT_RECORDED"
        )

    result_root = execution_root / "provider-execution-results-v1"
    if result_root.is_dir():
        for result_path in result_root.glob("*.json"):
            try:
                result = json.loads(result_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(result, Mapping):
                continue
            if (
                str(result.get("attempt_id") or "") == historical_attempt_id
                or str(result.get("unit_id") or "") == media_unit_id
            ):
                raise ProviderAttemptReconciliationError(
                    "TERMINAL_REJECTION_RESULT_ALREADY_MATERIALIZED"
                )

    path = reconciliation_ledger_path(repo, episode_id)
    with _THREAD_LOCK, _process_lock(path):
        rows = read_reconciliation_receipts(repo, episode_id)
        for row in reversed(rows):
            if str(row.get("historical_attempt_id") or "") != historical_attempt_id:
                continue
            if (
                row.get("provider_request_id") == provider_request_id
                and row.get("finding") == "PROVIDER_TERMINAL_REJECTION_NO_CHARGE"
                and row.get("original_submission_status")
                == PROVEN_SUBMITTED_TERMINAL_REJECTED
                and row.get("original_charge_status") == PROVEN_NOT_CHARGED
                and row.get("request_status")
                == TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED
                and row.get("provider_operation_id") == provider_operation_id
                and row.get("provider_error_code") == provider_error_code
                and row.get("provider_error_response_sha256") == evidence_sha
                and canonical_sha256(row.get("binding") or {})
                == canonical_sha256(dict(binding))
            ):
                return row
            raise ProviderAttemptReconciliationError(
                "CONFLICTING_RECONCILIATION_ALREADY_EXISTS"
            )

        previous = rows[-1] if rows else None
        relative_evidence = str(evidence_path.relative_to(repo)).replace("\\", "/")
        unsigned: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": str(uuid.uuid4()),
            "episode_id": episode_id,
            "stage": "PROVIDER_EXECUTION",
            "event": "PROVIDER_TERMINAL_REJECTION_RECONCILIATION",
            "timestamp_utc": utc_now(),
            "evidence_source": DURABLE_PROVIDER_TERMINAL_REJECTION,
            "provider": provider,
            "model": model,
            "media_type": media_type,
            "historical_attempt_id": historical_attempt_id,
            "provider_request_id": provider_request_id,
            "shot_id": shot_id,
            "media_unit_id": media_unit_id,
            "planned_cost_usd": planned_cost,
            "historical_attempt_spend_usd": 0.0,
            "planned_future_request_cost_usd": planned_cost,
            "provider_operation_id": provider_operation_id,
            "failed_poll_attempt_id": failed_poll_attempt_id,
            "provider_error_code": provider_error_code,
            "provider_error_response_path": relative_evidence,
            "provider_error_response_sha256": evidence_sha,
            "provider_error_response": dict(evidence),
            "finding": "PROVIDER_TERMINAL_REJECTION_NO_CHARGE",
            "human_conclusion": None,
            "original_submission_status": PROVEN_SUBMITTED_TERMINAL_REJECTED,
            "original_charge_status": PROVEN_NOT_CHARGED,
            "request_status": TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED,
            "terminal_provider_rejection": True,
            "safe_to_reauthorize": True,
            "explicit_no_charge_statement": True,
            "billable_output_detected": False,
            "historical_unknown_preserved": False,
            "historical_attempt_reusable": False,
            "new_attempt_required_for_future_submission": True,
            "attempt_ordinal_consumed": True,
            "replacement_authorized": False,
            "explicit_human_reauthorization_required": True,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
            "binding": dict(binding),
            "historical_evidence_references": {
                "provider_error_response": {
                    "path": relative_evidence,
                    "sha256": evidence_sha,
                },
                "failed_poll_attempt_id": failed_poll_attempt_id,
                "provider_operation_id": provider_operation_id,
            },
            "previous_receipt_sha256": (
                str(previous.get("receipt_sha256")) if previous else None
            ),
            "production_resumed": False,
            "provider_calls": 0,
            "paid_attempts_created": 0,
        }
        unsigned["receipt_sha256"] = canonical_sha256(unsigned)
        payload = canonical_json_bytes(unsigned) + b"\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            import os

            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
        return unsigned


def append_human_provider_account_review(
    repo_root: Path,
    episode_id: str,
    *,
    historical_attempt_id: str,
    provider_request_id: str,
    shot_id: str,
    media_unit_id: str,
    provider: str,
    model: str,
    media_type: str,
    planned_cost_usd: float,
    original_invalid_planning_task_uuid: str,
    historical_evidence: Mapping[str, Any],
    binding: Mapping[str, Any],
    historical_evidence_references: Mapping[str, Any],
) -> dict[str, Any]:
    """Append one idempotent human-account reconciliation receipt.

    ``binding`` is captured by the caller from the current authoritative
    preflight/ledger.  It is evidence context, not a transition-ledger write.
    A conflicting second review for the same attempt is rejected rather than
    silently replacing the first human conclusion.
    """

    if not historical_attempt_id or not provider_request_id:
        raise ProviderAttemptReconciliationError("RECONCILIATION_IDENTITY_REQUIRED")
    if not isinstance(historical_evidence, Mapping) or not historical_evidence:
        raise ProviderAttemptReconciliationError("HUMAN_PROVIDER_EVIDENCE_REQUIRED")
    if not isinstance(binding, Mapping) or not binding:
        raise ProviderAttemptReconciliationError("RECONCILIATION_BINDING_REQUIRED")
    if not isinstance(historical_evidence_references, Mapping):
        raise ProviderAttemptReconciliationError("HISTORICAL_EVIDENCE_REFERENCES_INVALID")
    try:
        planned_cost = float(planned_cost_usd)
    except (TypeError, ValueError) as exc:
        raise ProviderAttemptReconciliationError("PLANNED_COST_INVALID") from exc
    if planned_cost < 0:
        raise ProviderAttemptReconciliationError("PLANNED_COST_NEGATIVE")

    repo = Path(repo_root).resolve()
    ledger = ledger_path(repo, episode_id)
    if not ledger.is_file():
        raise ProviderAttemptReconciliationError("AUTHORITATIVE_LEDGER_MISSING")
    current_ledger_head = sha256_file(ledger)
    bound_ledger_head = str(binding.get("ledger_head_sha256") or "")
    if not bound_ledger_head or bound_ledger_head != current_ledger_head:
        raise ProviderAttemptReconciliationError("STALE_RECONCILIATION_BINDING")

    path = reconciliation_ledger_path(repo, episode_id)
    with _THREAD_LOCK, _process_lock(path):
        rows = read_reconciliation_receipts(repo, episode_id)
        for row in reversed(rows):
            if str(row.get("historical_attempt_id") or "") != historical_attempt_id:
                continue
            # Exact duplicate human evidence is idempotent.  A conflicting
            # conclusion must never silently supersede the first receipt.
            if (
                row.get("provider_request_id") == provider_request_id
                and row.get("finding") == "NO_EPISODE_002_OPERATION_PRESENT"
                and row.get("original_submission_status") == PROVEN_NOT_SUBMITTED
                and row.get("original_charge_status") == PROVEN_NOT_CHARGED
                and canonical_sha256(row.get("binding") or {})
                == canonical_sha256(dict(binding))
            ):
                return row
            raise ProviderAttemptReconciliationError(
                "CONFLICTING_RECONCILIATION_ALREADY_EXISTS"
            )

        previous = rows[-1] if rows else None
        unsigned: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": str(uuid.uuid4()),
            "episode_id": episode_id,
            "stage": "PROVIDER_EXECUTION",
            "event": "HUMAN_PROVIDER_ACCOUNT_RECONCILIATION",
            "timestamp_utc": utc_now(),
            "evidence_source": HUMAN_PROVIDER_ACCOUNT_REVIEW,
            "provider": provider,
            "model": model,
            "media_type": media_type,
            "historical_attempt_id": historical_attempt_id,
            "provider_request_id": provider_request_id,
            "shot_id": shot_id,
            "media_unit_id": media_unit_id,
            "planned_cost_usd": planned_cost,
            "historical_attempt_spend_usd": 0.0,
            "planned_future_request_cost_usd": planned_cost,
            "original_invalid_planning_task_uuid": original_invalid_planning_task_uuid,
            "provider_operation_id": None,
            "read_only_provider_lookup_performed": False,
            "human_evidence": dict(historical_evidence),
            "finding": "NO_EPISODE_002_OPERATION_PRESENT",
            "visible_completed_operations": "EPISODE_001_ONLY",
            "human_conclusion": "ORIGINAL_EP002_REQUEST_NOT_ACCEPTED_OR_CREATED_BY_RUNWARE",
            "original_submission_status": PROVEN_NOT_SUBMITTED,
            "original_charge_status": PROVEN_NOT_CHARGED,
            "request_status": NOT_SUBMITTED_ELIGIBLE,
            "historical_unknown_preserved": True,
            "historical_attempt_reusable": False,
            "new_attempt_required_for_future_submission": True,
            "attempt_ordinal_consumed": False,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
            "binding": dict(binding),
            "historical_evidence_references": dict(historical_evidence_references),
            "previous_receipt_sha256": (
                str(previous.get("receipt_sha256")) if previous else None
            ),
            "production_resumed": False,
            "provider_calls": 0,
            "paid_attempts_created": 0,
        }
        unsigned["receipt_sha256"] = canonical_sha256(unsigned)
        payload = canonical_json_bytes(unsigned) + b"\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            import os

            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
        return unsigned


__all__ = [
    "HUMAN_PROVIDER_ACCOUNT_REVIEW",
    "NOT_SUBMITTED_ELIGIBLE",
    "PROVEN_NOT_CHARGED",
    "PROVEN_NOT_SUBMITTED",
    "ProviderAttemptReconciliationError",
    "RECONCILIATION_LEDGER",
    "SCHEMA_VERSION",
    "append_human_provider_account_review",
    "current_reconciliation_receipts",
    "read_reconciliation_receipts",
    "reconciliation_for_attempt",
    "reconciliation_for_request",
    "reconciliation_ledger_path",
]
