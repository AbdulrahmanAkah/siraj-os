"""SIRAJ V4+ paid-provider preparation and authorization layer.

No automatic paid retry is implemented. Provider task/request UUIDs are
persisted to an exclusive lock and to the append-only ledger before a billable
submission may occur.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_v4_plus_attempt_ledger_v1 import (
    append_event,
    assert_submission_authorized,
)
from src.application.siraj_v4_plus_contract_v1 import EpisodeContext
from src.application.siraj_v4_plus_preflight_v1 import run_pre_spend_gate

SCHEMA_VERSION = "siraj-v4-plus-provider-executor-v1"
QUEUE_REL = Path("orchestration/media-production-queue-v3.json")
AUTH_REL = Path("orchestration/paid-authorization-v3.json")
LEDGER_REL = Path("orchestration/paid-attempt-ledger-v1.jsonl")
LOCK_ROOT_REL = Path("orchestration/provider-execution-v3/locks")
RETRY_AUTH_ROOT_REL = Path(
    "orchestration/provider-execution-v3/retry-authorizations"
)

class V4PlusProviderExecutionError(RuntimeError):
    pass

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise V4PlusProviderExecutionError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise V4PlusProviderExecutionError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value

def _write_new(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise V4PlusProviderExecutionError(
            f"EXCLUSIVE_FILE_ALREADY_EXISTS:{path}"
        ) from exc
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)

def _context(
    repo: Path,
    context_rel: Path,
) -> tuple[EpisodeContext, Path]:
    ctx = EpisodeContext.from_json(repo / context_rel)
    return ctx, repo / ctx.episode_root_rel

def _queue_items(queue: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = queue.get("items")
    if (
        not isinstance(items, list)
        or not all(isinstance(item, dict) for item in items)
    ):
        raise V4PlusProviderExecutionError(
            "V3_UNIFIED_MEDIA_QUEUE_ITEMS_REQUIRED"
        )
    return items

def _find_item(
    queue: Mapping[str, Any],
    queue_id: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in _queue_items(queue)
        if str(item.get("queue_id") or "") == queue_id
    ]
    if len(matches) != 1:
        raise V4PlusProviderExecutionError(
            f"QUEUE_ITEM_UNIQUE_REQUIRED:{queue_id}:{len(matches)}"
        )
    return matches[0]

def _attempts(
    ledger_path: Path,
    queue_id: str,
) -> set[int]:
    if not ledger_path.exists():
        return set()
    out: set[int] = set()
    for line in ledger_path.read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            row.get("queue_id") == queue_id
            and row.get("state")
            in {
                "SUBMITTING",
                "SUBMITTED",
                "COMPLETED",
                "FAILED",
                "TIMEOUT",
            }
        ):
            attempt = int(row.get("attempt_no", 0))
            if attempt > 0:
                out.add(attempt)
    return out

def record_consolidated_authorization(
    repo_root: Path,
    context_rel: Path,
    *,
    confirmed_maximum_usd: float,
) -> Path:
    repo = repo_root.resolve()
    run_pre_spend_gate(repo, context_rel)
    ctx, root = _context(repo, context_rel)
    queue = _read(root / QUEUE_REL)
    if str(queue.get("episode_id") or "") != ctx.episode_id:
        raise V4PlusProviderExecutionError(
            "QUEUE_EPISODE_MISMATCH"
        )
    if str(queue.get("generation_id") or "") != ctx.generation_id:
        raise V4PlusProviderExecutionError(
            "QUEUE_GENERATION_MISMATCH"
        )

    paid = [
        item
        for item in _queue_items(queue)
        if str(item.get("provider") or "").upper()
        in {"RUNWARE", "ELEVENLABS"}
        and str(item.get("status") or "") != "COMPLETE"
    ]
    if not paid:
        raise V4PlusProviderExecutionError(
            "NO_PENDING_PAID_QUEUE_ITEMS"
        )

    planned = round(
        sum(
            float(item.get("maximum_authorized_usd") or 0)
            for item in paid
        ),
        6,
    )
    if abs(float(confirmed_maximum_usd) - planned) > 1e-6:
        raise V4PlusProviderExecutionError(
            "CONSOLIDATED_AUTHORIZATION_MAXIMUM_MISMATCH:"
            f"{planned:.6f}:{float(confirmed_maximum_usd):.6f}"
        )

    auth_id = str(uuid.uuid4())
    auth_path = root / AUTH_REL
    if auth_path.exists():
        raise V4PlusProviderExecutionError(
            "PAID_AUTHORIZATION_ALREADY_EXISTS"
        )

    _write_new(
        auth_path,
        {
            "schema_version":
                "siraj-v4-plus-paid-authorization-v1",
            "episode_id": ctx.episode_id,
            "generation_id": ctx.generation_id,
            "authorization_id": auth_id,
            "status": "ACTIVE",
            "authorized_at_utc": _now(),
            "maximum_authorized_usd": planned,
            "automatic_paid_retry": False,
            "hidden_paid_retry": False,
            "authorized_queue_ids": [
                str(item["queue_id"]) for item in paid
            ],
            "authorization_source":
                "EXPLICIT_HUMAN_CONFIRMATION",
        },
    )

    ledger = root / LEDGER_REL
    for item in paid:
        append_event(
            ledger,
            {
                "queue_id": str(item["queue_id"]),
                "provider":
                    str(item["provider"]).upper(),
                "attempt_no": 1,
                "state": "AUTHORIZED",
                "authorization_id": auth_id,
                "authorization_kind": "INITIAL",
                "maximum_authorized_usd":
                    float(
                        item.get(
                            "maximum_authorized_usd"
                        )
                        or 0
                    ),
                "generation_id": ctx.generation_id,
            },
        )
    return auth_path

def record_queue_retry_authorization(
    repo_root: Path,
    context_rel: Path,
    *,
    queue_id: str,
    attempt_no: int,
    confirmed_maximum_usd: float,
    reason: str,
) -> Path:
    if int(attempt_no) <= 1:
        raise V4PlusProviderExecutionError(
            "RETRY_ATTEMPT_NUMBER_MUST_EXCEED_ONE"
        )
    if not str(reason).strip():
        raise V4PlusProviderExecutionError(
            "RETRY_REASON_REQUIRED"
        )

    repo = repo_root.resolve()
    run_pre_spend_gate(repo, context_rel)
    ctx, root = _context(repo, context_rel)
    queue = _read(root / QUEUE_REL)
    item = _find_item(queue, queue_id)
    maximum = float(
        item.get("maximum_authorized_usd") or 0
    )
    if (
        abs(
            float(confirmed_maximum_usd) - maximum
        )
        > 1e-9
    ):
        raise V4PlusProviderExecutionError(
            "RETRY_MAXIMUM_MISMATCH"
        )

    ledger = root / LEDGER_REL
    expected = len(_attempts(ledger, queue_id)) + 1
    if int(attempt_no) != expected:
        raise V4PlusProviderExecutionError(
            "RETRY_ATTEMPT_SEQUENCE_INVALID:"
            f"{expected}:{attempt_no}"
        )

    auth_id = str(uuid.uuid4())
    path = (
        root
        / RETRY_AUTH_ROOT_REL
        / f"{queue_id}-attempt-{attempt_no:02d}.json"
    )
    _write_new(
        path,
        {
            "schema_version":
                "siraj-v4-plus-queue-retry-authorization-v1",
            "episode_id": ctx.episode_id,
            "generation_id": ctx.generation_id,
            "queue_id": queue_id,
            "attempt_no": int(attempt_no),
            "authorization_id": auth_id,
            "authorization_kind":
                "QUEUE_SPECIFIC_RETRY",
            "status": "ACTIVE",
            "maximum_authorized_usd": maximum,
            "reason": str(reason).strip(),
            "authorized_at_utc": _now(),
            "authorization_source":
                "EXPLICIT_HUMAN_CONFIRMATION",
        },
    )
    append_event(
        ledger,
        {
            "queue_id": queue_id,
            "provider":
                str(item.get("provider") or "").upper(),
            "attempt_no": int(attempt_no),
            "state": "AUTHORIZED",
            "authorization_id": auth_id,
            "authorization_kind":
                "QUEUE_SPECIFIC_RETRY",
            "maximum_authorized_usd": maximum,
            "generation_id": ctx.generation_id,
        },
    )
    return path

def prepare_paid_submission(
    repo_root: Path,
    context_rel: Path,
    *,
    queue_id: str,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    preflight = run_pre_spend_gate(
        repo,
        context_rel,
    )
    ctx, root = _context(repo, context_rel)
    queue = _read(root / QUEUE_REL)
    item = _find_item(queue, queue_id)

    provider = str(
        item.get("provider") or ""
    ).upper()
    if provider not in {"RUNWARE", "ELEVENLABS"}:
        raise V4PlusProviderExecutionError(
            f"PAID_PROVIDER_REQUIRED:{provider}"
        )
    if str(item.get("status") or "") == "COMPLETE":
        raise V4PlusProviderExecutionError(
            "QUEUE_ITEM_ALREADY_COMPLETE"
        )

    ledger = root / LEDGER_REL
    attempt_no = (
        len(_attempts(ledger, queue_id)) + 1
    )

    if attempt_no == 1:
        auth = _read(root / AUTH_REL)
        auth_id = str(
            auth.get("authorization_id") or ""
        )
        if queue_id not in list(
            auth.get("authorized_queue_ids") or []
        ):
            raise V4PlusProviderExecutionError(
                "QUEUE_NOT_IN_CONSOLIDATED_AUTHORIZATION"
            )
    else:
        retry_path = (
            root
            / RETRY_AUTH_ROOT_REL
            / f"{queue_id}-attempt-{attempt_no:02d}.json"
        )
        retry = _read(retry_path)
        auth_id = str(
            retry.get("authorization_id") or ""
        )

    assert_submission_authorized(
        ledger,
        queue_id,
        attempt_no,
        auth_id,
    )

    external_id = str(uuid.uuid4())
    task_draft = item.get("task_draft")
    if not isinstance(task_draft, Mapping):
        raise V4PlusProviderExecutionError(
            "TASK_DRAFT_REQUIRED"
        )

    payload = dict(task_draft)
    if provider == "RUNWARE":
        payload["taskUUID"] = external_id
        payload["deliveryMethod"] = "async"
        payload["includeCost"] = True
    else:
        payload["sirajRequestUUID"] = external_id

    lock_path = (
        root
        / LOCK_ROOT_REL
        / f"{queue_id}-attempt-{attempt_no:02d}.json"
    )
    lock = {
        "schema_version":
            "siraj-v4-plus-provider-submission-lock-v1",
        "episode_id": ctx.episode_id,
        "generation_id": ctx.generation_id,
        "queue_id": queue_id,
        "provider": provider,
        "attempt_no": attempt_no,
        "authorization_id": auth_id,
        "external_task_or_request_uuid":
            external_id,
        "status": "LOCKED_BEFORE_NETWORK",
        "maximum_authorized_usd":
            float(
                item.get(
                    "maximum_authorized_usd"
                )
                or 0
            ),
        "created_at_utc": _now(),
        "automatic_retry": False,
        "preflight_status":
            preflight.get("status"),
        "request_payload": payload,
    }
    _write_new(lock_path, lock)

    append_event(
        ledger,
        {
            "queue_id": queue_id,
            "provider": provider,
            "attempt_no": attempt_no,
            "state": "SUBMITTING",
            "authorization_id": auth_id,
            "external_task_or_request_uuid":
                external_id,
            "maximum_authorized_usd":
                lock["maximum_authorized_usd"],
            "generation_id": ctx.generation_id,
            "lock_path_relative":
                str(
                    lock_path.relative_to(repo)
                ).replace("\\", "/"),
        },
    )

    return {
        "status": "PREPARED_NO_NETWORK_CALL",
        "episode_id": ctx.episode_id,
        "generation_id": ctx.generation_id,
        "queue_id": queue_id,
        "provider": provider,
        "attempt_no": attempt_no,
        "authorization_id": auth_id,
        "external_task_or_request_uuid":
            external_id,
        "lock_path": lock_path,
        "request_payload": payload,
    }

def record_submission_result(
    repo_root: Path,
    context_rel: Path,
    *,
    queue_id: str,
    attempt_no: int,
    state: str,
    provider_task_uuid: str | None = None,
    actual_cost_usd: float | None = None,
    detail: str = "",
) -> None:
    allowed = {
        "SUBMITTED",
        "COMPLETED",
        "FAILED",
        "TIMEOUT",
    }
    if state not in allowed:
        raise V4PlusProviderExecutionError(
            f"SUBMISSION_RESULT_STATE_INVALID:{state}"
        )

    repo = repo_root.resolve()
    ctx, root = _context(repo, context_rel)
    item = _find_item(
        _read(root / QUEUE_REL),
        queue_id,
    )
    append_event(
        root / LEDGER_REL,
        {
            "queue_id": queue_id,
            "provider":
                str(
                    item.get("provider") or ""
                ).upper(),
            "attempt_no": int(attempt_no),
            "state": state,
            "provider_task_uuid":
                provider_task_uuid,
            "actual_cost_usd":
                actual_cost_usd,
            "detail": str(detail),
            "generation_id":
                ctx.generation_id,
        },
    )
