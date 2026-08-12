"""SIRAJ V6.6 R9 true execution telemetry.

This module is deliberately write-only from execution code and read-only from the UI.
It does not infer work from stage state. Each event is emitted at the point where the
operation actually happens.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import uuid
from typing import Any, Mapping

from src.application.telemetry_outbox import (
    emit as emit_outbox_event,
    outbox_path,
    projection_path,
    read_events as read_outbox_events,
    read_projection,
)

_LOCK = threading.RLock()
STATE_NAME = "production-live-state-v6.json"
EVENTS_NAME = "production-live-events-v6.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _root(repo_root: Path, episode_id: str) -> Path:
    repo = Path(repo_root).resolve()
    if not episode_id or episode_id == "NEXT_NEW_EPISODE":
        return repo / "projects" / "_series"
    return repo / "projects" / episode_id / "orchestration"


def live_paths(repo_root: Path, episode_id: str) -> tuple[Path, Path]:
    if episode_id and episode_id != "NEXT_NEW_EPISODE":
        return (
            projection_path(repo_root, episode_id),
            outbox_path(repo_root, episode_id),
        )
    root = _root(repo_root, episode_id)
    return root / STATE_NAME, root / EVENTS_NAME


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(
        path.name
        + f".{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _append(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()


def _clean_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def emit_event(
    repo_root: Path,
    episode_id: str,
    event_type: str,
    *,
    stage: str | None = None,
    message_ar: str | None = None,
    operation: str | None = None,
    progress_current: int | float | None = None,
    progress_total: int | float | None = None,
    input_path: Any = None,
    output_path: Any = None,
    last_completed_file: Any = None,
    provider: str | None = None,
    model: str | None = None,
    task_uuid: str | None = None,
    request_current: int | None = None,
    request_total: int | None = None,
    expected_cost_usd: float | None = None,
    actual_cost_usd: float | None = None,
    status: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a typed outbox event without changing production outcome."""
    now = _now()
    event: dict[str, Any] = {
        "schema_version": "siraj-production-live-event-v6.6-r9",
        "timestamp_utc": now,
        "event_type": str(event_type),
        "episode_id": str(episode_id),
    }
    optional = {
        "stage": stage,
        "message_ar": message_ar,
        "operation": operation,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "input_path": _clean_path(input_path),
        "output_path": _clean_path(output_path),
        "last_completed_file": _clean_path(
            last_completed_file
            if last_completed_file is not None
            else (output_path if event_type == "FILE_WRITTEN" else None)
        ),
        "provider": provider,
        "model": model,
        "task_uuid": task_uuid,
        "request_current": request_current,
        "request_total": request_total,
        "expected_cost_usd": expected_cost_usd,
        "actual_cost_usd": actual_cost_usd,
        "status": status,
    }
    event.update({k: v for k, v in optional.items() if v is not None})
    if details:
        event["details"] = dict(details)

    persisted = emit_outbox_event(
        repo_root,
        episode_id,
        event_type,
        {key: value for key, value in event.items() if key not in {"schema_version", "timestamp_utc", "event_type", "episode_id"}},
    )
    event["telemetry_persisted"] = persisted
    return event


def read_live_state(repo_root: Path, episode_id: str) -> dict[str, Any] | None:
    if episode_id and episode_id != "NEXT_NEW_EPISODE":
        projected = read_projection(repo_root, episode_id)
        if projected is not None:
            return projected
    path = _root(repo_root, episode_id) / STATE_NAME
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def recent_events(repo_root: Path, episode_id: str, limit: int = 12) -> list[dict[str, Any]]:
    if episode_id and episode_id != "NEXT_NEW_EPISODE":
        try:
            events = read_outbox_events(repo_root, episode_id)
        except Exception:
            events = []
        if events:
            flattened: list[dict[str, Any]] = []
            for event in events[-max(1, int(limit)):]:
                row = dict(event.get("payload") or {})
                row.update(
                    {
                        "timestamp_utc": event.get("timestamp_utc"),
                        "event_type": event.get("event_type"),
                        "episode_id": event.get("episode_id"),
                    }
                )
                flattened.append(row)
            return flattened
    path = _root(repo_root, episode_id) / EVENTS_NAME
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    for line in lines[-max(1, int(limit)):]:
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            result.append(row)
    return result
