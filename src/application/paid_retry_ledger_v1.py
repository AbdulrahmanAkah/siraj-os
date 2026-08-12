"""Append-only, attempt-bound paid retry authorization ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
import uuid

from src.application.artifact_provenance_v1 import (
    append_jsonl,
    canonical_sha256,
    read_jsonl,
    sha256_file,
    utc_now,
    write_new_json,
)


SCHEMA_VERSION = "siraj-paid-retry-ledger-v1"
AUTH_SCHEMA_VERSION = "siraj-paid-retry-authorization-v1"
CONFIRMATION_PHRASE = "أوافق على إعادة المحاولة المدفوعة لهذه المحاولة المحددة"


class PaidRetryLedgerError(RuntimeError):
    pass


def ledger_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "paid-retry-attempt-ledger-v1.jsonl"
    )


def authorization_root(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "paid-retry-authorizations-v1"
    )


def record_retry_required(
    repo_root: Path,
    episode_id: str,
    *,
    stage: str,
    prior_attempt_id: str,
    prior_status: str,
    prior_payload_hash: str,
    failure_classification: str,
) -> dict[str, Any]:
    if prior_status not in {"FAILED", "UNKNOWN", "NETWORK_RESULT_UNKNOWN"}:
        raise PaidRetryLedgerError("PRIOR_STATUS_NOT_RETRY_GUARDED")
    value: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "event_type": "RETRY_AUTHORIZATION_REQUIRED",
        "episode_id": episode_id,
        "stage": stage,
        "prior_attempt_id": prior_attempt_id,
        "prior_status": prior_status,
        "prior_payload_hash": prior_payload_hash,
        "failure_classification": failure_classification,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "timestamp_utc": utc_now(),
    }
    value["event_sha256"] = canonical_sha256(value)
    append_jsonl(ledger_path(repo_root, episode_id), value)
    return value


def retry_required_for_attempt(
    repo_root: Path,
    episode_id: str,
    prior_attempt_id: str,
) -> bool:
    state = None
    for row in read_jsonl(ledger_path(repo_root, episode_id)):
        if row.get("prior_attempt_id") == prior_attempt_id:
            state = row.get("event_type")
    return state == "RETRY_AUTHORIZATION_REQUIRED"


def authorize_exact_retry(
    repo_root: Path,
    episode_id: str,
    *,
    stage: str,
    prior_attempt_id: str,
    new_attempt_id: str,
    payload_hash: str,
    reason: str,
    confirmation_phrase: str,
) -> Path:
    if confirmation_phrase.strip() != CONFIRMATION_PHRASE:
        raise PaidRetryLedgerError("RETRY_CONFIRMATION_PHRASE_MISMATCH")
    if not retry_required_for_attempt(repo_root, episode_id, prior_attempt_id):
        raise PaidRetryLedgerError("RETRY_GUARD_FOR_ATTEMPT_REQUIRED")
    if not reason.strip():
        raise PaidRetryLedgerError("RETRY_REASON_REQUIRED")
    authorization_id = str(uuid.uuid4())
    value: dict[str, Any] = {
        "schema_version": AUTH_SCHEMA_VERSION,
        "authorization_id": authorization_id,
        "status": "ACTIVE",
        "episode_id": episode_id,
        "stage": stage,
        "prior_attempt_id": prior_attempt_id,
        "new_attempt_id": new_attempt_id,
        "payload_hash": payload_hash,
        "reason": reason.strip(),
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "authorized_at_utc": utc_now(),
    }
    value["authorization_sha256"] = canonical_sha256(value)
    path = authorization_root(repo_root, episode_id) / f"{authorization_id}.json"
    write_new_json(path, value)
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "event_type": "RETRY_AUTHORIZED",
        "episode_id": episode_id,
        "stage": stage,
        "prior_attempt_id": prior_attempt_id,
        "new_attempt_id": new_attempt_id,
        "payload_hash": payload_hash,
        "authorization_path": str(path),
        "authorization_sha256": sha256_file(path),
        "timestamp_utc": utc_now(),
    }
    event["event_sha256"] = canonical_sha256(event)
    append_jsonl(ledger_path(repo_root, episode_id), event)
    return path


def authorization_reference(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PaidRetryLedgerError("RETRY_AUTHORIZATION_OBJECT_REQUIRED")
    signature = value.get("authorization_sha256")
    unsigned = {key: val for key, val in value.items() if key != "authorization_sha256"}
    if signature != canonical_sha256(unsigned):
        raise PaidRetryLedgerError("RETRY_AUTHORIZATION_HASH_INVALID")
    return {
        "path": str(Path(path).resolve()),
        "sha256": sha256_file(Path(path)),
        "status": value.get("status"),
        "prior_attempt_id": value.get("prior_attempt_id"),
        "new_attempt_id": value.get("new_attempt_id"),
        "payload_hash": value.get("payload_hash"),
        "reason": value.get("reason"),
        "authorization_id": value.get("authorization_id"),
    }


def record_retry_transport_state(
    repo_root: Path,
    episode_id: str,
    *,
    prior_attempt_id: str,
    new_attempt_id: str,
    event_type: str,
) -> None:
    if event_type not in {
        "RETRY_RESERVED",
        "RETRY_REQUEST_BYTES_HANDED_TO_TRANSPORT",
        "RETRY_RESULT_PERSISTED",
        "RETRY_FAILED_OR_UNKNOWN",
    }:
        raise PaidRetryLedgerError("RETRY_TRANSPORT_EVENT_INVALID")
    value: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "episode_id": episode_id,
        "prior_attempt_id": prior_attempt_id,
        "new_attempt_id": new_attempt_id,
        "timestamp_utc": utc_now(),
    }
    value["event_sha256"] = canonical_sha256(value)
    append_jsonl(ledger_path(repo_root, episode_id), value)
