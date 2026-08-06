"""Offline audit and safe recovery of stale ElevenLabs TTS locks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from src.application.elevenlabs_key_validation_recovery_v1 import (
    classify_elevenlabs_invalid_key_prefix_rejection,
    reset_terminal_invalid_elevenlabs_attempt_for_explicit_reauthorization,
)

RELEASE = "SIRAJ_ADAM_STALE_TTS_LOCK_AUDIT_V2"


class StaleTtsLockAuditError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StaleTtsLockAuditError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise StaleTtsLockAuditError(f"JSON_OBJECT_REQUIRED:{path}")
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


def _is_nonterminal_status(status: str) -> bool:
    normalized = status.upper()
    markers = (
        "LOCKED",
        "SUBMITTED",
        "POLLING",
        "NETWORK_RESULT_UNKNOWN",
        "UNKNOWN_NO_AUTOMATIC_RESUBMISSION",
    )
    return any(marker in normalized for marker in markers)


def audit_and_recover(
    repo: Path,
    *,
    episode_id: str,
) -> dict[str, Any]:
    repo = repo.resolve()
    episode = repo / "projects" / episode_id
    lock_root = (
        episode
        / "orchestration"
        / "media-execution"
        / "locks"
    )
    receipt_root = (
        episode
        / "orchestration"
        / "media-execution"
        / "receipts"
    )

    if not lock_root.is_dir():
        return {
            "release": RELEASE,
            "episode_id": episode_id,
            "status": "PASS_NO_TTS_LOCKS",
            "tts_locks_found": 0,
            "invalid_key_locks_archived": 0,
            "nonterminal_locks_requiring_manual_review": 0,
            "provider_requests": 0,
            "paid_provider_requests": 0,
            "items": [],
        }

    items: list[dict[str, Any]] = []
    archived_count = 0
    manual_review_count = 0

    for path in sorted(lock_root.glob("*.json")):
        payload = _read(path)
        if str(payload.get("media_kind") or "") != "ELEVENLABS_TTS":
            continue

        status = str(payload.get("status") or "")
        queue_id = str(payload.get("queue_id") or "")
        relative = str(path.relative_to(repo)).replace("\\", "/")
        classification = classify_elevenlabs_invalid_key_prefix_rejection(
            {
                "status": status,
                "last_error": payload.get("last_error"),
                "provider_rejection_code": payload.get(
                    "provider_rejection_code"
                ),
            }
        )

        if classification is not None:
            archive = (
                reset_terminal_invalid_elevenlabs_attempt_for_explicit_reauthorization(
                    path
                )
            )
            if archive is None:
                raise StaleTtsLockAuditError(
                    f"INVALID_KEY_LOCK_ARCHIVE_FAILED:{relative}"
                )
            archived_count += 1
            items.append(
                {
                    "queue_id": queue_id,
                    "original_path": relative,
                    "status_before": status,
                    "classification": "INVALID_KEY_TERMINAL",
                    "action": "ARCHIVED_AND_ACTIVE_LOCK_RELEASED",
                    "archive_path": str(
                        archive.relative_to(repo)
                    ).replace("\\", "/"),
                    "provider_request_billed": False,
                }
            )
            continue

        receipt_candidates = (
            list(receipt_root.glob(f"{path.stem}*-receipt.json"))
            if receipt_root.is_dir()
            else []
        )
        if receipt_candidates:
            items.append(
                {
                    "queue_id": queue_id,
                    "original_path": relative,
                    "status_before": status,
                    "classification": "LOCK_WITH_RECEIPT",
                    "action": "LEFT_UNCHANGED",
                    "receipt_paths": [
                        str(value.relative_to(repo)).replace("\\", "/")
                        for value in receipt_candidates
                    ],
                }
            )
            continue

        if _is_nonterminal_status(status):
            manual_review_count += 1
            items.append(
                {
                    "queue_id": queue_id,
                    "original_path": relative,
                    "status_before": status,
                    "classification": "NONTERMINAL_OR_UNKNOWN",
                    "action": "LEFT_UNCHANGED_MANUAL_REVIEW_REQUIRED",
                }
            )
            continue

        items.append(
            {
                "queue_id": queue_id,
                "original_path": relative,
                "status_before": status,
                "classification": "OTHER_TERMINAL",
                "action": "LEFT_UNCHANGED",
            }
        )

    active_after = []
    if lock_root.is_dir():
        for path in sorted(lock_root.glob("*.json")):
            try:
                payload = _read(path)
            except StaleTtsLockAuditError:
                continue
            if str(payload.get("media_kind") or "") == "ELEVENLABS_TTS":
                active_after.append(
                    str(path.relative_to(repo)).replace("\\", "/")
                )

    status = (
        "PASS_INVALID_KEY_LOCKS_ARCHIVED"
        if manual_review_count == 0
        else "BLOCKED_MANUAL_LOCK_REVIEW_REQUIRED"
    )

    report = {
        "release": RELEASE,
        "episode_id": episode_id,
        "status": status,
        "tts_locks_found": len(items),
        "invalid_key_locks_archived": archived_count,
        "nonterminal_locks_requiring_manual_review": manual_review_count,
        "active_tts_locks_after_recovery": active_after,
        "active_tts_lock_count_after_recovery": len(active_after),
        "provider_requests": 0,
        "paid_provider_requests": 0,
        "hidden_paid_retry": "FORBIDDEN",
        "items": items,
    }

    report_path = (
        episode
        / "orchestration"
        / "stale-tts-lock-audit-v2.json"
    )
    _write(report_path, report)
    report["report_path"] = str(
        report_path.relative_to(repo)
    ).replace("\\", "/")
    return report
