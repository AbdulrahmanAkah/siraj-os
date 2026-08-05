from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

RELEASE = "SIRAJ_ELEVENLABS_KEY_VALIDATION_AND_RECOVERY_V1"
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
EXECUTION_ROOT_REL = Path("orchestration/media-execution")
BACKUP_ROOT_REL = Path(
    "projects/_orchestrator/elevenlabs-key-recovery-backups"
)
READY_STATUS = "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"


class ElevenLabsKeyValidationError(RuntimeError):
    pass


class ElevenLabsKeyRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ElevenLabsInvalidKeyRecoveryResult:
    episode_id: str | None
    invalid_locks_found: int
    terminal_locks_archived: int
    queue_items_reset: int
    paid_items_reset: int
    provider_requests: int
    state_backup_path: Path | None
    queue_backup_path: Path | None
    archive_paths: tuple[Path, ...]
    runtime_status: str
    runtime_stage: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("state_backup_path", "queue_backup_path"):
            value = payload[key]
            payload[key] = str(value) if value is not None else None
        payload["archive_paths"] = [str(value) for value in self.archive_paths]
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ElevenLabsKeyRecoveryError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise ElevenLabsKeyRecoveryError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def normalize_and_validate_elevenlabs_api_key(
    value: str,
    *,
    source: str = "INPUT",
) -> str:
    secret = str(value or "").strip()
    if not secret:
        raise ElevenLabsKeyValidationError(
            f"ELEVENLABS_API_KEY_REQUIRED:{source}"
        )
    if not secret.startswith("sk_"):
        raise ElevenLabsKeyValidationError(
            "ELEVENLABS_API_KEY_INVALID_PREFIX:"
            + source
            + ":EXPECTED_PREFIX_sk_"
        )
    if any(character.isspace() for character in secret):
        raise ElevenLabsKeyValidationError(
            f"ELEVENLABS_API_KEY_CONTAINS_WHITESPACE:{source}"
        )
    return secret


def classify_elevenlabs_invalid_key_prefix_rejection(
    value: Any,
) -> dict[str, Any] | None:
    if isinstance(value, (Mapping, Sequence)) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            text = str(value)
    else:
        text = str(value or "")
    lowered = text.lower()
    markers = (
        "invalid_api_key_prefix",
        "api key must start with 'sk_'",
        'api key must start with "sk_"',
        "expected_prefix_sk_",
    )
    if not any(marker in lowered for marker in markers):
        return None
    return {
        "code": "ELEVENLABS_INVALID_API_KEY_PREFIX",
        "safe_to_reauthorize": True,
        "provider_request_billed": False,
        "requires_new_key": True,
    }


def reset_terminal_invalid_elevenlabs_attempt_for_explicit_reauthorization(
    lock_path: Path,
) -> Path | None:
    path = lock_path.resolve()
    if not path.is_file():
        return None
    lock = _read(path)
    if str(lock.get("media_kind", "")) != "ELEVENLABS_TTS":
        return None
    rejection = classify_elevenlabs_invalid_key_prefix_rejection(
        {
            "status": lock.get("status"),
            "last_error": lock.get("last_error"),
            "provider_rejection_code": lock.get("provider_rejection_code"),
        }
    )
    if rejection is None:
        return None
    archive_root = path.parent / "terminal-rejections"
    archive_root.mkdir(parents=True, exist_ok=True)
    archive = archive_root / f"{path.stem}-{_stamp()}-invalid-key.json"
    counter = 1
    while archive.exists():
        archive = archive_root / (
            f"{path.stem}-{_stamp()}-invalid-key-{counter:02d}.json"
        )
        counter += 1
    lock.update(
        {
            "status": "ARCHIVED_TERMINAL_INVALID_KEY_REJECTION",
            "provider_rejection_code": rejection["code"],
            "safe_to_reauthorize": True,
            "provider_request_billed": False,
            "archived_at_utc": _now(),
            "active_lock_released": True,
        }
    )
    _write(archive, lock)
    path.unlink()
    return archive


def _backup(path: Path, root: Path) -> Path | None:
    if not path.is_file():
        return None
    destination = root / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination


def _queue_items(queue: Mapping[str, Any]) -> list[dict[str, Any]]:
    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        raise ElevenLabsKeyRecoveryError("MEDIA_QUEUE_COLLECTIONS_REQUIRED")
    values = queues.get("elevenlabs_tts")
    if not isinstance(values, list):
        raise ElevenLabsKeyRecoveryError("ELEVENLABS_QUEUE_LIST_REQUIRED")
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            raise ElevenLabsKeyRecoveryError("ELEVENLABS_QUEUE_ITEM_OBJECT_REQUIRED")
        result.append(value)
    return result


def recover_invalid_elevenlabs_attempts(
    repo_root: Path,
) -> ElevenLabsInvalidKeyRecoveryResult:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        return ElevenLabsInvalidKeyRecoveryResult(
            episode_id=None,
            invalid_locks_found=0,
            terminal_locks_archived=0,
            queue_items_reset=0,
            paid_items_reset=0,
            provider_requests=0,
            state_backup_path=None,
            queue_backup_path=None,
            archive_paths=(),
            runtime_status=str(state.get("status", "")),
            runtime_stage=str(state.get("stage", "")),
        )
    episode_id = episode_id.strip()
    episode_root = repo / "projects" / episode_id
    queue_path = episode_root / MEDIA_QUEUE_REL
    queue = _read(queue_path)
    items = {str(item.get("queue_id", "")): item for item in _queue_items(queue)}
    lock_root = episode_root / EXECUTION_ROOT_REL / "locks"
    candidates = tuple(sorted(lock_root.glob("*-attempt-01.json"))) if lock_root.is_dir() else ()
    invalid: list[Path] = []
    for path in candidates:
        try:
            lock = _read(path)
        except ElevenLabsKeyRecoveryError:
            continue
        if str(lock.get("media_kind", "")) != "ELEVENLABS_TTS":
            continue
        if classify_elevenlabs_invalid_key_prefix_rejection(lock) is not None:
            invalid.append(path)

    if not invalid:
        return ElevenLabsInvalidKeyRecoveryResult(
            episode_id=episode_id,
            invalid_locks_found=0,
            terminal_locks_archived=0,
            queue_items_reset=0,
            paid_items_reset=0,
            provider_requests=0,
            state_backup_path=None,
            queue_backup_path=None,
            archive_paths=(),
            runtime_status=str(state.get("status", "")),
            runtime_stage=str(state.get("stage", "")),
        )

    backup_root = repo / BACKUP_ROOT_REL / _stamp()
    state_backup = _backup(state_path, backup_root / "state")
    queue_backup = _backup(queue_path, backup_root / "queue")
    archive_paths: list[Path] = []
    reset = 0
    for lock_path in invalid:
        lock = _read(lock_path)
        queue_id = str(lock.get("queue_id", ""))
        item = items.get(queue_id)
        archive = reset_terminal_invalid_elevenlabs_attempt_for_explicit_reauthorization(
            lock_path
        )
        if archive is None:
            continue
        archive_paths.append(archive)
        if item is None or str(item.get("status", "")) == "COMPLETE":
            continue
        item.update(
            {
                "status": READY_STATUS,
                "last_error": None,
                "invalid_key_rejection_recovered": True,
                "invalid_key_lock_archive_path_relative": str(
                    archive.relative_to(repo)
                ).replace("\\", "/"),
                "requires_new_elevenlabs_key": True,
                "recovered_at_utc": _now(),
            }
        )
        for key in (
            "request_id",
            "task_uuid",
            "completed_at_utc",
            "receipt_path_relative",
            "actual_cost_usd",
            "estimated_cost_usd",
            "output_sha256",
        ):
            item.pop(key, None)
        reset += 1

    if reset:
        _write(queue_path, queue)
        state.update(
            {
                "status": "DESKTOP_MEDIA_EXECUTION_ACTIVE",
                "stage": "DESKTOP_MEDIA_EXECUTION",
                "next_stage": "DESKTOP_MEDIA_EXECUTION_V1",
                "last_error": None,
                "elevenlabs_key_recovery_release": RELEASE,
                "elevenlabs_key_recovery_status": "NEW_VALID_KEY_REQUIRED",
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)

    return ElevenLabsInvalidKeyRecoveryResult(
        episode_id=episode_id,
        invalid_locks_found=len(invalid),
        terminal_locks_archived=len(archive_paths),
        queue_items_reset=reset,
        paid_items_reset=0,
        provider_requests=0,
        state_backup_path=state_backup,
        queue_backup_path=queue_backup,
        archive_paths=tuple(archive_paths),
        runtime_status=str(state.get("status", "")),
        runtime_stage=str(state.get("stage", "")),
    )
