"""Append-only paid-attempt and cost ledger for SIRAJ V4+."""
from __future__ import annotations
import json, os, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "siraj-paid-attempt-ledger-v1"

class PaidAttemptLedgerError(RuntimeError):
    pass

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise PaidAttemptLedgerError(f"LEDGER_CORRUPT_LINE:{n}:{exc}") from exc
    return out

def append_event(path: Path, event: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(event)
    row.setdefault("schema_version", SCHEMA_VERSION)
    row.setdefault("event_id", str(uuid.uuid4()))
    row.setdefault("timestamp_utc", _now())
    for key in ("queue_id", "provider", "attempt_no", "state"):
        if row.get(key) in (None, ""):
            raise PaidAttemptLedgerError(f"LEDGER_FIELD_REQUIRED:{key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY)
    try:
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    return row

def assert_submission_authorized(
    path: Path, queue_id: str, attempt_no: int, authorization_id: str
) -> None:
    if not authorization_id:
        raise PaidAttemptLedgerError("EXPLICIT_AUTHORIZATION_REQUIRED")
    events = _events(path)
    auth = [
        x for x in events
        if x.get("queue_id") == queue_id
        and x.get("state") == "AUTHORIZED"
        and x.get("authorization_id") == authorization_id
    ]
    if not auth:
        raise PaidAttemptLedgerError(f"AUTHORIZATION_NOT_FOUND:{queue_id}")
    submitted = [
        x for x in events
        if x.get("queue_id") == queue_id
        and x.get("state") in {"SUBMITTING", "SUBMITTED", "COMPLETED", "FAILED", "TIMEOUT"}
    ]
    distinct_attempts = {int(x.get("attempt_no", 0)) for x in submitted}
    if attempt_no != len(distinct_attempts) + 1:
        raise PaidAttemptLedgerError(f"ATTEMPT_NUMBER_INVALID:{queue_id}:{attempt_no}")
    if attempt_no > 1:
        retries = [
            x for x in auth
            if x.get("authorization_kind") == "QUEUE_SPECIFIC_RETRY"
            and int(x.get("attempt_no", 0)) == attempt_no
        ]
        if not retries:
            raise PaidAttemptLedgerError(
                f"QUEUE_SPECIFIC_RETRY_AUTH_REQUIRED:{queue_id}:{attempt_no}"
            )

def reconcile_provider_operations(
    path: Path, provider_operation_count: int
) -> dict[str, int]:
    events = _events(path)
    authorized = sum(1 for x in events if x.get("state") == "AUTHORIZED")
    submitted = len({
        (x.get("queue_id"), x.get("attempt_no"))
        for x in events
        if x.get("state") in {"SUBMITTING", "SUBMITTED", "COMPLETED", "FAILED", "TIMEOUT"}
    })
    if provider_operation_count > authorized:
        raise PaidAttemptLedgerError(
            f"PROVIDER_OPERATION_COUNT_EXCEEDS_AUTHORIZED:"
            f"{provider_operation_count}:{authorized}"
        )
    return {
        "authorized": authorized,
        "submitted": submitted,
        "provider_operations": provider_operation_count,
    }
