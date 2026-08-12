"""Durable telemetry outbox and typed state projection.

Production truth is committed by its owner first.  Telemetry is then appended
to this outbox.  A telemetry failure is reported as degraded observability and
must never reclassify a provider or stage result.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Mapping
import uuid

from src.application.artifact_provenance_v1 import (
    append_jsonl,
    atomic_write_json,
    canonical_sha256,
    read_jsonl,
    utc_now,
)


SCHEMA_VERSION = "siraj-telemetry-event-v1"

EVENT_TYPES = frozenset(
    {
        "RESUME_ACTION_RECEIVED",
        "CONTROLLED_ALIGNMENT_VALIDATION_AUTHORIZED",
        "CONTROLLED_ALIGNMENT_VALIDATION_STOPPED",
        "WORKER_LAUNCH_REQUESTED",
        "WORKER_START_RETURNED",
        "WORKER_THREAD_ENTERED",
        "WORKER_HEARTBEAT",
        "WORKER_START_FAILED",
        "STAGE_STARTED",
        "TASK_STARTED",
        "FILE_READING",
        "FILE_WRITTEN",
        "PAID_ATTEMPT_RESERVED",
        "RESULT_PERSISTED",
        "PROVIDER_TRANSPORT_STARTED",
        "LUNA_REQUEST_STARTED",
        "LUNA_RESPONSE_RECEIVED",
        "RUNWARE_TASK_SUBMITTED",
        "RUNWARE_POLLING",
        "ASSET_DOWNLOADED",
        "MONTAGE_SHOT_RENDERING",
        "QA_CHECK_RUNNING",
        "ALIGNMENT_LOCAL_VALIDATION_STARTED",
        "ALIGNMENT_LOCAL_VALIDATION_COMPLETED",
        "TASK_COMPLETED",
        "STAGE_COMPLETED",
        "STAGE_FAILED",
        "WORKER_FINISHED",
        "WORKER_FAILED",
    }
)

EVENT_ALIASES = {
    "RUNWARE_TASK_SUBMISSION_STARTED": "PROVIDER_TRANSPORT_STARTED",
    "RUNWARE_TASK_POLLING": "RUNWARE_POLLING",
    "LUNA_TASK_COMPLETED": "TASK_COMPLETED",
    "RUNWARE_TASK_COMPLETED": "TASK_COMPLETED",
    "MONTAGE_TASK_COMPLETED": "TASK_COMPLETED",
}

TASK_FIELDS = {
    "provider",
    "model",
    "task_uuid",
    "attempt_id",
    "request_current",
    "request_total",
    "expected_cost_usd",
    "actual_cost_usd",
    "input_path",
    "output_path",
}


class TelemetryOutboxError(RuntimeError):
    pass


def outbox_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "production-telemetry-outbox-v1.jsonl"
    )


def projection_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "production-live-state-v1.json"
    )


def normalize_event_type(event_type: str) -> str:
    normalized = EVENT_ALIASES.get(str(event_type), str(event_type))
    if normalized.startswith("WORKER_STATE_PROBE_"):
        return "WORKER_HEARTBEAT"
    if normalized not in EVENT_TYPES:
        raise TelemetryOutboxError("TELEMETRY_EVENT_TYPE_INVALID:" + normalized)
    return normalized


def build_event(
    episode_id: str,
    event_type: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = normalize_event_type(event_type)
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "episode_id": episode_id,
        "event_type": normalized,
        "original_event_type": event_type if event_type != normalized else None,
        "timestamp_utc": utc_now(),
        "payload": {key: value for key, value in payload.items() if value is not None},
    }
    event["event_sha256"] = canonical_sha256(event)
    return event


def _validate_event(event: Mapping[str, Any]) -> None:
    if event.get("schema_version") != SCHEMA_VERSION:
        raise TelemetryOutboxError("TELEMETRY_SCHEMA_INVALID")
    unsigned = {key: value for key, value in event.items() if key != "event_sha256"}
    if event.get("event_sha256") != canonical_sha256(unsigned):
        raise TelemetryOutboxError("TELEMETRY_EVENT_HASH_INVALID")
    normalize_event_type(str(event.get("event_type") or ""))


def project_events(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": "siraj-telemetry-projection-v1",
        "status": "IDLE",
    }
    for event in events:
        _validate_event(event)
        event_type = str(event["event_type"])
        payload = dict(event.get("payload") or {})
        if event_type in {
            "STAGE_STARTED",
            "STAGE_COMPLETED",
            "STAGE_FAILED",
            "WORKER_FINISHED",
            "WORKER_FAILED",
        }:
            last_task = {
                key: state.get(key)
                for key in TASK_FIELDS
                if state.get(key) is not None
            }
            for key in TASK_FIELDS:
                state.pop(key, None)
            if last_task:
                state["last_task"] = last_task
        state.update(payload)
        state.update(
            {
                "episode_id": event["episode_id"],
                "last_event_type": event_type,
                "last_event_id": event["event_id"],
                "updated_at_utc": event["timestamp_utc"],
            }
        )
        if event_type == "WORKER_THREAD_ENTERED":
            state["worker_state"] = "RUNNING"
        elif event_type == "WORKER_HEARTBEAT":
            state["worker_state"] = "RUNNING"
            state["last_worker_heartbeat_utc"] = event["timestamp_utc"]
        elif event_type == "WORKER_START_FAILED":
            state["worker_state"] = "FAILED"
        elif event_type in {"WORKER_FINISHED", "WORKER_FAILED"}:
            state["worker_state"] = "FINISHED" if event_type == "WORKER_FINISHED" else "FAILED"
    return state


def read_events(repo_root: Path, episode_id: str) -> list[dict[str, Any]]:
    events = read_jsonl(outbox_path(repo_root, episode_id))
    for event in events:
        _validate_event(event)
    return events


def rebuild_projection(repo_root: Path, episode_id: str) -> dict[str, Any]:
    state = project_events(read_events(repo_root, episode_id))
    atomic_write_json(
        projection_path(repo_root, episode_id),
        state,
        preserve_previous=True,
    )
    return state


def emit(
    repo_root: Path,
    episode_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    project: bool = True,
) -> bool:
    """Best-effort telemetry after production truth; never raises to caller."""

    try:
        event = build_event(episode_id, event_type, payload)
        append_jsonl(outbox_path(repo_root, episode_id), event)
        if project:
            rebuild_projection(repo_root, episode_id)
        return True
    except Exception as exc:
        print(
            "SIRAJ_TELEMETRY_DEGRADED:"
            + type(exc).__name__
            + ":"
            + str(exc),
            file=sys.stderr,
        )
        return False


def read_projection(repo_root: Path, episode_id: str) -> dict[str, Any] | None:
    path = projection_path(repo_root, episode_id)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
