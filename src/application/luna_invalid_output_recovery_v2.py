"""Explicit one-request recovery for an invalid Luna JSON response.

This module never authorizes itself. It only exposes:
- inspection of an eligible invalid-output lock;
- creation of a supplemental authorization after explicit user confirmation;
- archival of the failed lock immediately before one replacement request;
- fail-closed consumption of that authorization before network activity.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from src.application.luna_cinematic_prompt_director_v2 import (
    CinematicPromptDirectorError,
    EPISODE_ID,
    PROMPT_LOCK_DIR_REL,
    execute_authorized_batch as _base_execute_authorized_batch,
)


RELEASE = "SIRAJ_EXPLICIT_LUNA_INVALID_OUTPUT_RETRY_V2"
SUPPLEMENTAL_MAXIMUM_USD = 0.05
SUPPLEMENTAL_AUTH_REL = Path(
    "evidence/luna-invalid-output-supplemental-authorization-v2.json"
)
ARCHIVE_DIR_REL = Path(
    "orchestration/luna-prompt-direction-v2/locks/archive"
)
ELIGIBLE_STATUS = "INVALID_LUNA_OUTPUT_NO_AUTOMATIC_RETRY"


class LunaExplicitRetryError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LunaExplicitRetryError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise LunaExplicitRetryError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
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
    os.replace(temporary, path)


def inspect_invalid_luna_retry(
    repo_root: Path,
    episode_id: str = EPISODE_ID,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    episode_root = repo / "projects" / episode_id
    lock_dir = episode_root / PROMPT_LOCK_DIR_REL
    authorization_path = episode_root / SUPPLEMENTAL_AUTH_REL

    eligible: list[tuple[Path, dict[str, Any]]] = []
    if lock_dir.is_dir():
        for path in sorted(
            lock_dir.glob("LUNA-PROMPT-BATCH-*.json")
        ):
            lock = _read(path)
            if str(lock.get("status") or "") == ELIGIBLE_STATUS:
                eligible.append((path, lock))

    if len(eligible) > 1:
        raise LunaExplicitRetryError(
            "MULTIPLE_INVALID_LUNA_LOCKS_REQUIRE_MANUAL_REVIEW"
        )
    if not eligible:
        return {
            "status": "NO_EXPLICIT_LUNA_RETRY_REQUIRED",
            "retry_required": False,
            "supplemental_maximum_usd": 0.0,
        }

    lock_path, lock = eligible[0]
    authorization = (
        _read(authorization_path)
        if authorization_path.is_file()
        else None
    )
    authorization_status = (
        str(authorization.get("status") or "")
        if isinstance(authorization, Mapping)
        else ""
    )
    if authorization_status in {
        "CONSUMED_BEFORE_NETWORK",
        "COMPLETE",
        "FAILED_AFTER_CONSUMPTION",
    }:
        return {
            "status": (
                "EXPLICIT_LUNA_RETRY_ALREADY_CONSUMED_"
                "MANUAL_REVIEW_REQUIRED"
            ),
            "retry_required": False,
            "manual_review_required": True,
            "batch_id": str(lock.get("batch_id") or ""),
            "lock_path": str(lock_path),
            "authorization_path": str(authorization_path),
            "authorization_status": authorization_status,
            "supplemental_maximum_usd": 0.0,
        }

    return {
        "status": "EXPLICIT_SUPPLEMENTAL_AUTHORIZATION_REQUIRED",
        "retry_required": True,
        "manual_review_required": False,
        "batch_id": str(lock.get("batch_id") or ""),
        "lock_path": str(lock_path),
        "failed_status": str(lock.get("status") or ""),
        "failed_error": str(lock.get("last_error") or ""),
        "provider_requests_made": int(
            lock.get("provider_requests_made", 0) or 0
        ),
        "original_response_recoverable": False,
        "supplemental_maximum_usd": SUPPLEMENTAL_MAXIMUM_USD,
        "authorization_path": str(authorization_path),
    }


def create_explicit_retry_authorization(
    repo_root: Path,
    *,
    episode_id: str,
    batch_id: str,
    confirmed_supplemental_usd: float,
    effective_consolidated_maximum_usd: float,
    episode_hard_cap_usd: float,
) -> Path:
    if abs(
        float(confirmed_supplemental_usd)
        - SUPPLEMENTAL_MAXIMUM_USD
    ) > 1e-9:
        raise LunaExplicitRetryError(
            "LUNA_RETRY_SUPPLEMENTAL_MAXIMUM_MISMATCH"
        )
    if (
        float(effective_consolidated_maximum_usd)
        > float(episode_hard_cap_usd) + 1e-9
    ):
        raise LunaExplicitRetryError(
            "LUNA_RETRY_EFFECTIVE_MAXIMUM_EXCEEDS_HARD_CAP"
        )

    repo = repo_root.resolve()
    episode_root = repo / "projects" / episode_id
    inspection = inspect_invalid_luna_retry(
        repo,
        episode_id,
    )
    if inspection.get("retry_required") is not True:
        raise LunaExplicitRetryError(
            "LUNA_INVALID_OUTPUT_RETRY_NOT_ELIGIBLE:"
            + str(inspection.get("status") or "")
        )
    if str(inspection.get("batch_id") or "") != batch_id:
        raise LunaExplicitRetryError(
            "LUNA_INVALID_OUTPUT_RETRY_BATCH_MISMATCH"
        )

    path = episode_root / SUPPLEMENTAL_AUTH_REL
    if path.is_file():
        existing = _read(path)
        if (
            str(existing.get("status") or "") == "ACTIVE"
            and str(existing.get("batch_id") or "") == batch_id
            and abs(
                float(
                    existing.get(
                        "maximum_authorized_usd",
                        0.0,
                    )
                )
                - SUPPLEMENTAL_MAXIMUM_USD
            )
            <= 1e-9
        ):
            return path
        raise LunaExplicitRetryError(
            "LUNA_RETRY_AUTHORIZATION_ALREADY_EXISTS_OR_USED"
        )

    _write(
        path,
        {
            "schema_version": (
                "siraj-luna-invalid-output-"
                "supplemental-authorization-v2"
            ),
            "release": RELEASE,
            "episode_id": episode_id,
            "batch_id": batch_id,
            "status": "ACTIVE",
            "decision": (
                "AUTHORIZED_EXACTLY_ONE_REPLACEMENT_REQUEST_"
                "AFTER_INVALID_JSON_OUTPUT"
            ),
            "retry_attempt_index": 2,
            "maximum_provider_requests": 1,
            "maximum_authorized_usd": SUPPLEMENTAL_MAXIMUM_USD,
            "effective_consolidated_maximum_usd": (
                effective_consolidated_maximum_usd
            ),
            "episode_hard_cap_usd": episode_hard_cap_usd,
            "automatic_retry": "FORBIDDEN",
            "hidden_paid_retry": "FORBIDDEN",
            "authorization_source": (
                "EXPLICIT_DESKTOP_CONFIRMATION"
            ),
            "authorized_at_utc": _now(),
        },
    )
    return path


def execute_authorized_batch_with_explicit_retry(
    repo_root: Path,
    *,
    episode_id: str,
    batch_id: str,
    api_key: str,
    confirmed_maximum_usd: float,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    episode_root = repo / "projects" / episode_id
    lock_path = (
        episode_root
        / PROMPT_LOCK_DIR_REL
        / f"{batch_id}.json"
    )

    retry_attempt = False
    authorization_path = episode_root / SUPPLEMENTAL_AUTH_REL
    if lock_path.is_file():
        lock = _read(lock_path)
        if str(lock.get("status") or "") != ELIGIBLE_STATUS:
            return _base_execute_authorized_batch(
                repo,
                episode_id=episode_id,
                batch_id=batch_id,
                api_key=api_key,
                confirmed_maximum_usd=confirmed_maximum_usd,
            )

        if not authorization_path.is_file():
            raise CinematicPromptDirectorError(
                "LUNA_INVALID_OUTPUT_EXPLICIT_REAUTHORIZATION_REQUIRED"
            )
        authorization = _read(authorization_path)
        if str(authorization.get("status") or "") != "ACTIVE":
            raise CinematicPromptDirectorError(
                "LUNA_INVALID_OUTPUT_RETRY_AUTHORIZATION_NOT_ACTIVE"
            )
        if str(authorization.get("batch_id") or "") != batch_id:
            raise CinematicPromptDirectorError(
                "LUNA_INVALID_OUTPUT_RETRY_BATCH_MISMATCH"
            )
        if abs(
            float(
                authorization.get(
                    "maximum_authorized_usd",
                    0.0,
                )
            )
            - SUPPLEMENTAL_MAXIMUM_USD
        ) > 1e-9:
            raise CinematicPromptDirectorError(
                "LUNA_INVALID_OUTPUT_RETRY_MAXIMUM_MISMATCH"
            )

        archive_dir = episode_root / ARCHIVE_DIR_REL
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / (
            f"{batch_id}-attempt-01-invalid-json.json"
        )
        if archive_path.exists():
            raise CinematicPromptDirectorError(
                "LUNA_INVALID_OUTPUT_ARCHIVE_ALREADY_EXISTS"
            )
        _write(archive_path, lock)

        authorization["status"] = "CONSUMED_BEFORE_NETWORK"
        authorization["consumed_at_utc"] = _now()
        authorization["archived_failed_lock_path"] = str(
            archive_path
        )
        _write(authorization_path, authorization)
        lock_path.unlink()
        retry_attempt = True

    try:
        result = _base_execute_authorized_batch(
            repo,
            episode_id=episode_id,
            batch_id=batch_id,
            api_key=api_key,
            confirmed_maximum_usd=confirmed_maximum_usd,
        )
    except Exception as exc:
        if retry_attempt and authorization_path.is_file():
            authorization = _read(authorization_path)
            authorization["status"] = "FAILED_AFTER_CONSUMPTION"
            authorization["last_error"] = str(exc)
            authorization["failed_at_utc"] = _now()
            _write(authorization_path, authorization)
        raise

    if retry_attempt and authorization_path.is_file():
        authorization = _read(authorization_path)
        authorization["status"] = "COMPLETE"
        authorization["completed_at_utc"] = _now()
        authorization["result"] = dict(result)
        _write(authorization_path, authorization)
        result = dict(result)
        result["explicit_retry_attempt"] = 2
        result["supplemental_authorization_path"] = str(
            authorization_path
        )
    return result
