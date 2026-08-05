from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

RELEASE = "SIRAJ_RUNWARE_SEEDREAM_NEGATIVE_PROMPT_RECOVERY_V1"
SEEDREAM_MODELS = frozenset({"bytedance:seedream@5.0-pro"})
REJECTION_CODE = "unsupportedArchitectureNegativePrompt"
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
EXECUTION_ROOT_REL = Path("orchestration/media-execution")
REPORT_REL = Path("orchestration/runware-seedream-negative-prompt-recovery-v1.json")
BACKUP_ROOT_REL = Path(
    "projects/_orchestrator/runware-seedream-negative-prompt-recovery-backups"
)


class SeedreamNegativePromptRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SeedreamNegativePromptRecoveryResult:
    episode_id: str
    seedream_tasks_sanitized: int
    terminal_locks_archived: int
    queue_items_reset: int
    provider_requests: int
    state_status: str
    state_stage: str
    report_path: Path
    backup_root: Path

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["report_path"] = str(self.report_path)
        payload["backup_root"] = str(self.backup_root)
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeedreamNegativePromptRecoveryError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise SeedreamNegativePromptRecoveryError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
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


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(value)


def prepare_runware_task_for_submission(
    task: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(task)
    model = str(result.get("model", "")).strip()
    if model in SEEDREAM_MODELS:
        result.pop("negativePrompt", None)
        routing = result.get("sirajRouting")
        if isinstance(routing, Mapping):
            routing_copy = dict(routing)
            routing_copy["negative_prompt_policy"] = (
                "OMITTED_UNSUPPORTED_BY_MODEL_ARCHITECTURE"
            )
            result["sirajRouting"] = routing_copy
    return result


def classify_seedream_negative_prompt_rejection(
    value: Any,
    task: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    text = _text(value)
    model = str((task or {}).get("model", "")).strip()
    model_match = (
        model in SEEDREAM_MODELS
        or "seedream_5_pro" in text
        or "bytedance:seedream@5.0-pro" in text
    )
    if REJECTION_CODE not in text or not model_match:
        return None
    output_markers = ("imageURL", "imageUUID", '"cost":')
    has_output = any(marker in text for marker in output_markers)
    return {
        "code": REJECTION_CODE,
        "model": model or "bytedance:seedream@5.0-pro",
        "terminal": True,
        "safe_to_reauthorize": not has_output,
        "billable_output_detected": has_output,
    }


def _safe_queue_id(queue_id: str) -> str:
    return "".join(
        character
        for character in queue_id
        if character.isalnum() or character in "-_"
    )


def reset_terminal_rejected_attempt_for_explicit_reauthorization(
    lock_path: Path,
) -> Path | None:
    if not lock_path.is_file():
        return None
    lock = _read(lock_path)
    task: Mapping[str, Any] = {}
    request_payload = lock.get("request_payload")
    if isinstance(request_payload, list) and request_payload:
        first = request_payload[0]
        if isinstance(first, Mapping):
            task = first
    rejection = classify_seedream_negative_prompt_rejection(
        {
            "last_error": lock.get("last_error"),
            "provider_acknowledgement": lock.get("provider_acknowledgement"),
            "provider_rejection_code": lock.get("provider_rejection_code"),
        },
        task,
    )
    if rejection is None or not rejection["safe_to_reauthorize"]:
        return None
    history = lock_path.parent.parent / "rejected-history"
    history.mkdir(parents=True, exist_ok=True)
    destination = history / (
        lock_path.stem + "-" + _stamp() + "-terminal-rejected.json"
    )
    shutil.move(str(lock_path), str(destination))
    return destination


def _backup(repo: Path, source: Path, backup_root: Path) -> Path | None:
    if not source.is_file():
        return None
    relative = source.resolve().relative_to(repo.resolve())
    destination = backup_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def repair_runtime_seedream_negative_prompt_failure(
    repo_root: Path,
) -> SeedreamNegativePromptRecoveryResult:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = str(state.get("current_episode_id", "")).strip()
    if not episode_id:
        raise SeedreamNegativePromptRecoveryError("CURRENT_EPISODE_REQUIRED")
    episode_root = repo / "projects" / episode_id
    queue_path = episode_root / MEDIA_QUEUE_REL
    queue = _read(queue_path)
    backup_root = repo / BACKUP_ROOT_REL / _stamp()
    _backup(repo, state_path, backup_root)
    _backup(repo, queue_path, backup_root)

    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        raise SeedreamNegativePromptRecoveryError(
            "MEDIA_QUEUE_COLLECTIONS_REQUIRED"
        )
    images = queues.get("runware_images")
    if not isinstance(images, list):
        raise SeedreamNegativePromptRecoveryError(
            "RUNWARE_IMAGE_QUEUE_REQUIRED"
        )

    sanitized = 0
    archived = 0
    reset = 0
    for raw in images:
        if not isinstance(raw, dict):
            continue
        task = raw.get("task_draft")
        if not isinstance(task, Mapping):
            continue
        prepared = prepare_runware_task_for_submission(task)
        if prepared != dict(task):
            raw["task_draft"] = prepared
            raw["negative_prompt_policy"] = (
                "OMITTED_UNSUPPORTED_BY_MODEL_ARCHITECTURE"
            )
            sanitized += 1

        queue_id = str(raw.get("queue_id", "")).strip()
        if not queue_id:
            continue
        lock_path = (
            episode_root
            / EXECUTION_ROOT_REL
            / "locks"
            / f"{_safe_queue_id(queue_id)}-attempt-01.json"
        )
        if lock_path.is_file():
            _backup(repo, lock_path, backup_root)
            destination = (
                reset_terminal_rejected_attempt_for_explicit_reauthorization(
                    lock_path
                )
            )
            if destination is not None:
                archived += 1
                raw["status"] = (
                    "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
                )
                raw.pop("task_uuid", None)
                raw.pop("completed_at_utc", None)
                raw.pop("actual_cost_usd", None)
                raw.pop("estimated_cost_usd", None)
                raw.pop("output_sha256", None)
                raw["recovered_from_terminal_provider_rejection"] = True
                raw["recovery_reason"] = REJECTION_CODE
                raw["rejected_lock_archive_path_relative"] = str(
                    destination.resolve().relative_to(repo)
                ).replace("\\", "/")
                reset += 1

    if sanitized <= 0:
        raise SeedreamNegativePromptRecoveryError(
            "NO_SEEDREAM_TASK_DRAFT_REQUIRED_SANITIZATION"
        )

    queue["status"] = "READY_AWAITING_EXPLICIT_PAID_EXECUTION"
    queue["seedream_negative_prompt_policy"] = (
        "OMIT_NEGATIVE_PROMPT_FOR_SEEDREAM_5_PRO"
    )
    queue["updated_at_utc"] = _now()
    _write(queue_path, queue)

    state.update(
        {
            "status": "MEDIA_QUEUE_READY",
            "stage": "RUNWARE_IMAGE_GENERATION",
            "next_stage": "DESKTOP_MEDIA_EXECUTION_V1",
            "last_error": None,
            "seedream_negative_prompt_recovery": "COMPLETE",
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)

    report_path = episode_root / REPORT_REL
    report = {
        "schema_version": (
            "siraj-runware-seedream-negative-prompt-recovery-v1"
        ),
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "READY_FOR_NEW_EXPLICIT_MEDIA_AUTHORIZATION",
        "root_cause": (
            "SEEDREAM_5_PRO_REJECTS_NEGATIVE_PROMPT_PARAMETER"
        ),
        "seedream_tasks_sanitized": sanitized,
        "terminal_locks_archived": archived,
        "queue_items_reset": reset,
        "provider_requests": 0,
        "automatic_resubmission": "FORBIDDEN",
        "new_explicit_authorization_required": True,
        "backup_root_relative": str(
            backup_root.resolve().relative_to(repo)
        ).replace("\\", "/"),
        "created_at_utc": _now(),
    }
    _write(report_path, report)
    return SeedreamNegativePromptRecoveryResult(
        episode_id=episode_id,
        seedream_tasks_sanitized=sanitized,
        terminal_locks_archived=archived,
        queue_items_reset=reset,
        provider_requests=0,
        state_status=str(state["status"]),
        state_stage=str(state["stage"]),
        report_path=report_path,
        backup_root=backup_root,
    )
