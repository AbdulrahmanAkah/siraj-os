"""Episode-wide authorization law for SIRAJ V6.6.

One explicit human authorization covers all *initial* paid operations for the
episode from the current point through READY_FOR_FINAL_HUMAN_REVIEW.

It does NOT authorize:
- publishing,
- a paid retry after failed/unknown provider execution,
- re-running a completed stage,
- changing canonical architecture/policies.

Paid retry remains a separate explicit exception.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

FULL_EPISODE_CONFIRMATION_PHRASE = "أوافق على الإنتاج الكامل للحلقة"
PAID_RETRY_CONFIRMATION_PHRASE = "أوافق على إعادة المحاولة المدفوعة لهذه المرحلة"
NEXT_EPISODE_ID = "NEXT_NEW_EPISODE"


class EpisodeMasterAuthorizationV66Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise EpisodeMasterAuthorizationV66Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp, path)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def master_authorization_path(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    if episode_id == NEXT_EPISODE_ID:
        return (
            repo
            / "projects/_series/"
            "siraj-next-episode-master-authorization-v6-6.json"
        )
    return (
        repo
        / "projects"
        / episode_id
        / "orchestration/episode-master-paid-authorization-v6-6.json"
    )


def master_authorization_active(
    repo_root: Path,
    episode_id: str,
) -> bool:
    path = master_authorization_path(repo_root, episode_id)
    if not path.is_file():
        return False
    try:
        value = _read(path)
    except Exception:
        return False
    signature = value.get("authorization_sha256")
    unsigned = {
        key: val
        for key, val in value.items()
        if key != "authorization_sha256"
    }
    return (
        value.get("status") == "ACTIVE"
        and value.get("episode_id") == episode_id
        and isinstance(signature, str)
        and signature == canonical_sha256(unsigned)
        and value.get("automatic_paid_retry") is False
        and value.get("automatic_paid_resubmission") is False
        and value.get("publishing") == "HUMAN_ONLY"
    )


def authorize_episode_cycle(
    repo_root: Path,
    episode_id: str,
    current_stage: str,
    confirmation_phrase: str,
) -> Path:
    if confirmation_phrase.strip() != FULL_EPISODE_CONFIRMATION_PHRASE:
        raise EpisodeMasterAuthorizationV66Error(
            "FULL_EPISODE_CONFIRMATION_PHRASE_MISMATCH"
        )

    repo = Path(repo_root).resolve()
    path = master_authorization_path(repo, episode_id)

    if path.is_file():
        existing = _read(path)
        if (
            existing.get("status") == "ACTIVE"
            and existing.get("episode_id") == episode_id
            and existing.get("automatic_paid_retry") is False
            and existing.get("automatic_paid_resubmission") is False
        ):
            return path
        raise EpisodeMasterAuthorizationV66Error(
            "EXISTING_MASTER_AUTHORIZATION_CONFLICT"
        )

    payload = {
        "schema_version": "siraj-episode-master-paid-authorization-v6.6",
        "status": "ACTIVE",
        "episode_id": episode_id,
        "authorized_from_stage": current_stage,
        "scope": (
            "ALL_INITIAL_PAID_OPERATIONS_THROUGH_"
            "READY_FOR_FINAL_HUMAN_REVIEW"
        ),
        "providers": [
            "OPENAI_LUNA",
            "ELEVENLABS",
            "RUNWARE",
        ],
        "future_episode_event_review_gate": True,
        "event_discussion_with_luna": True,
        "post_event_approval_continues_automatically": True,
        "completed_stage_rerun": "FORBIDDEN",
        "paid_retry_included": False,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "assistant_authored_cost_cap_usd": None,
        "assistant_authored_call_cap": None,
        "publishing": "HUMAN_ONLY",
        "authorization_source": "EXPLICIT_HUMAN_DESKTOP_CONFIRMATION",
        "confirmation_phrase": FULL_EPISODE_CONFIRMATION_PHRASE,
        "authorized_at_utc": _now(),
    }
    payload["authorization_sha256"] = canonical_sha256(payload)
    _write(path, payload)
    return path


def migrate_next_episode_authorization(
    repo_root: Path,
    episode_id: str,
) -> Path | None:
    repo = Path(repo_root).resolve()
    source = master_authorization_path(repo, NEXT_EPISODE_ID)
    if not source.is_file():
        return None

    value = _read(source)
    if value.get("status") != "ACTIVE":
        raise EpisodeMasterAuthorizationV66Error(
            "NEXT_EPISODE_MASTER_AUTH_NOT_ACTIVE"
        )

    destination = master_authorization_path(repo, episode_id)
    if destination.is_file():
        existing = _read(destination)
        if existing.get("status") == "ACTIVE":
            return destination
        raise EpisodeMasterAuthorizationV66Error(
            "EPISODE_MASTER_AUTH_CONFLICT_ON_MIGRATION"
        )

    migrated = dict(value)
    migrated["episode_id"] = episode_id
    migrated["migrated_from"] = str(source.relative_to(repo))
    migrated["migrated_at_utc"] = _now()
    migrated["authorization_sha256"] = canonical_sha256(
        {
            key: val
            for key, val in migrated.items()
            if key != "authorization_sha256"
        }
    )
    _write(destination, migrated)

    value["status"] = "MIGRATED"
    value["migrated_episode_id"] = episode_id
    value["migrated_at_utc"] = _now()
    _write(source, value)
    return destination


def master_authorization_reference(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any]:
    path = master_authorization_path(repo_root, episode_id)
    if not path.is_file():
        raise EpisodeMasterAuthorizationV66Error(
            "MASTER_AUTHORIZATION_REQUIRED:" + episode_id
        )
    value = _read(path)
    signature = value.get("authorization_sha256")
    unsigned = {
        key: val
        for key, val in value.items()
        if key != "authorization_sha256"
    }
    if (
        value.get("status") != "ACTIVE"
        or value.get("episode_id") != episode_id
        or not isinstance(signature, str)
        or signature != canonical_sha256(unsigned)
    ):
        raise EpisodeMasterAuthorizationV66Error(
            "MASTER_AUTHORIZATION_NOT_ACTIVE_OR_TAMPERED:" + episode_id
        )
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "authorized_at_utc": value.get("authorized_at_utc"),
    }


def _episode_root(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
    )


def paid_retry_guard_path(
    repo_root: Path,
    episode_id: str,
) -> Path:
    return (
        _episode_root(repo_root, episode_id)
        / "paid-retry-required-v6-6.json"
    )


def paid_retry_authorization_path(
    repo_root: Path,
    episode_id: str,
) -> Path:
    return (
        _episode_root(repo_root, episode_id)
        / "paid-retry-authorization-v6-6.json"
    )


def mark_paid_failure(
    repo_root: Path,
    episode_id: str,
    stage: str,
    error: str,
) -> Path:
    if episode_id == NEXT_EPISODE_ID:
        raise EpisodeMasterAuthorizationV66Error(
            "CANNOT_MARK_RETRY_FOR_UNMATERIALIZED_EPISODE"
        )
    repo = Path(repo_root).resolve()
    master = master_authorization_reference(repo, episode_id)
    guard = {
        "schema_version": "siraj-paid-retry-required-v6.6",
        "status": "RETRY_AUTHORIZATION_REQUIRED",
        "episode_id": episode_id,
        "stage": stage,
        "error": str(error),
        "master_authorization_sha256": master["sha256"],
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "created_at_utc": _now(),
    }
    guard["guard_sha256"] = canonical_sha256(guard)
    path = paid_retry_guard_path(repo, episode_id)
    _write(path, guard)

    journal = (
        _episode_root(repo, episode_id)
        / "paid-retry-journal-v6-6.jsonl"
    )
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                guard,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    return path


def retry_required(
    repo_root: Path,
    episode_id: str,
    stage: str,
) -> bool:
    path = paid_retry_guard_path(repo_root, episode_id)
    if not path.is_file():
        return False
    try:
        value = _read(path)
    except Exception:
        return True
    return (
        value.get("status") == "RETRY_AUTHORIZATION_REQUIRED"
        and value.get("stage") == stage
    )


def retry_authorized(
    repo_root: Path,
    episode_id: str,
    stage: str,
) -> bool:
    guard_path = paid_retry_guard_path(repo_root, episode_id)
    auth_path = paid_retry_authorization_path(repo_root, episode_id)
    if not guard_path.is_file() or not auth_path.is_file():
        return False
    try:
        guard = _read(guard_path)
        auth = _read(auth_path)
    except Exception:
        return False
    return (
        guard.get("status") == "RETRY_AUTHORIZATION_REQUIRED"
        and guard.get("stage") == stage
        and auth.get("status") == "ACTIVE"
        and auth.get("stage") == stage
        and auth.get("guard_sha256") == guard.get("guard_sha256")
    )


def authorize_paid_retry(
    repo_root: Path,
    episode_id: str,
    stage: str,
    confirmation_phrase: str,
) -> Path:
    if confirmation_phrase.strip() != PAID_RETRY_CONFIRMATION_PHRASE:
        raise EpisodeMasterAuthorizationV66Error(
            "PAID_RETRY_CONFIRMATION_PHRASE_MISMATCH"
        )
    guard_path = paid_retry_guard_path(repo_root, episode_id)
    if not guard_path.is_file():
        raise EpisodeMasterAuthorizationV66Error(
            "PAID_RETRY_GUARD_NOT_FOUND"
        )
    guard = _read(guard_path)
    if (
        guard.get("status") != "RETRY_AUTHORIZATION_REQUIRED"
        or guard.get("stage") != stage
    ):
        raise EpisodeMasterAuthorizationV66Error(
            "PAID_RETRY_GUARD_INVALID"
        )

    path = paid_retry_authorization_path(repo_root, episode_id)
    payload = {
        "schema_version": "siraj-paid-retry-authorization-v6.6",
        "status": "ACTIVE",
        "episode_id": episode_id,
        "stage": stage,
        "guard_sha256": guard.get("guard_sha256"),
        "authorization_source": "EXPLICIT_HUMAN_DESKTOP_CONFIRMATION",
        "confirmation_phrase": PAID_RETRY_CONFIRMATION_PHRASE,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "authorized_at_utc": _now(),
    }
    _write(path, payload)
    return path


def consume_paid_retry_authorization(
    repo_root: Path,
    episode_id: str,
    stage: str,
) -> None:
    path = paid_retry_authorization_path(repo_root, episode_id)
    if not path.is_file():
        raise EpisodeMasterAuthorizationV66Error(
            "PAID_RETRY_AUTHORIZATION_REQUIRED"
        )
    value = _read(path)
    if (
        value.get("status") != "ACTIVE"
        or value.get("stage") != stage
    ):
        raise EpisodeMasterAuthorizationV66Error(
            "PAID_RETRY_AUTHORIZATION_INVALID"
        )
    value["status"] = "CONSUMED"
    value["consumed_at_utc"] = _now()
    _write(path, value)


def resolve_paid_retry_guard(
    repo_root: Path,
    episode_id: str,
    stage: str,
) -> None:
    guard_path = paid_retry_guard_path(repo_root, episode_id)
    if guard_path.is_file():
        value = _read(guard_path)
        if value.get("stage") == stage:
            value["status"] = "RESOLVED"
            value["resolved_at_utc"] = _now()
            _write(guard_path, value)
