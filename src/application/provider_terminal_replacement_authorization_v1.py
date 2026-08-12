from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "siraj-terminal-provider-replacement-authorization-v1"
CONSUMPTION_SCHEMA_VERSION = "siraj-terminal-provider-replacement-consumption-v1"
AUTH_FILENAME = "terminal-provider-replacement-authorization-v1.json"
CONSUMPTION_FILENAME = "terminal-provider-replacement-consumption-v1.jsonl"
_ALLOWED_PERSON_GENERATION = {"dont_allow", "allow_adult", "allow_all"}
_LOCK = threading.RLock()


class TerminalProviderReplacementAuthorizationError(RuntimeError):
    pass


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _execution_root(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / str(episode_id)
        / "orchestration"
        / "provider-execution-v1"
    )


def authorization_path(repo_root: Path, episode_id: str) -> Path:
    return _execution_root(repo_root, episode_id) / AUTH_FILENAME


def consumption_path(repo_root: Path, episode_id: str) -> Path:
    return _execution_root(repo_root, episode_id) / CONSUMPTION_FILENAME


def _unsigned_authorization(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("authorization_sha256", None)
    return result


def _unsigned_consumption(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("consumption_sha256", None)
    return result


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_CONSUMPTION_ROW_OBJECT_REQUIRED"
            )
        rows.append(value)
    return rows


def _nested_person_generation(task: Mapping[str, Any]) -> str:
    provider_settings = task.get("providerSettings")
    if not isinstance(provider_settings, Mapping):
        return ""
    google = provider_settings.get("google")
    if not isinstance(google, Mapping):
        return ""
    return str(google.get("personGeneration") or "")


def _validate_authorization(
    value: Mapping[str, Any],
    *,
    episode_id: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    row = dict(value)
    if row.get("schema_version") != SCHEMA_VERSION:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_SCHEMA_INVALID"
        )
    if str(row.get("episode_id") or "") != str(episode_id):
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_EPISODE_MISMATCH"
        )
    if row.get("stage") != "PROVIDER_EXECUTION":
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_STAGE_MISMATCH"
        )
    if row.get("status") != "AUTHORIZED":
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_STATUS_INVALID"
        )
    if request_id is not None:
        observed = str(
            row.get("provider_request_id")
            or row.get("media_unit_id")
            or ""
        )
        if observed != str(request_id):
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_AUTHORIZATION_REQUEST_MISMATCH"
            )

    expected_hash = _canonical_sha256(_unsigned_authorization(row))
    if str(row.get("authorization_sha256") or "") != expected_hash:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_HASH_INVALID"
        )

    for key in (
        "authorization_id",
        "replacement_attempt_id",
        "replacement_provider_task_uuid",
        "historical_attempt_id",
    ):
        try:
            parsed = uuid.UUID(str(row.get(key) or ""))
        except (ValueError, TypeError, AttributeError) as exc:
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_AUTHORIZATION_UUID_INVALID:" + key
            ) from exc
        if key == "replacement_provider_task_uuid" and parsed.version != 4:
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_PROVIDER_TASK_UUID4_REQUIRED"
            )

    if int(row.get("maximum_provider_requests") or 0) != 1:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_ONE_REQUEST_ONLY"
        )
    planned = float(row.get("planned_cost_usd") or -1.0)
    maximum = float(row.get("maximum_cost_usd") or -1.0)
    if planned < 0 or maximum < 0 or planned > maximum + 1e-9:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_COST_INVALID"
        )
    if row.get("automatic_paid_retry") is not False:
        raise TerminalProviderReplacementAuthorizationError(
            "AUTOMATIC_PAID_RETRY_MUST_BE_FALSE"
        )
    if row.get("automatic_paid_resubmission") is not False:
        raise TerminalProviderReplacementAuthorizationError(
            "AUTOMATIC_PAID_RESUBMISSION_MUST_BE_FALSE"
        )
    if row.get("historical_attempt_reusable") is not False:
        raise TerminalProviderReplacementAuthorizationError(
            "HISTORICAL_ATTEMPT_MUST_NOT_BE_REUSABLE"
        )

    historical_prompt = str(row.get("historical_positive_prompt") or "")
    if not historical_prompt:
        raise TerminalProviderReplacementAuthorizationError(
            "HISTORICAL_POSITIVE_PROMPT_REQUIRED"
        )
    if _text_sha256(historical_prompt) != str(
        row.get("historical_positive_prompt_sha256") or ""
    ):
        raise TerminalProviderReplacementAuthorizationError(
            "HISTORICAL_POSITIVE_PROMPT_HASH_INVALID"
        )

    replacement_prompt = str(row.get("replacement_positive_prompt") or "")
    if not replacement_prompt:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PROMPT_REQUIRED"
        )
    if _text_sha256(replacement_prompt) != str(
        row.get("replacement_positive_prompt_sha256") or ""
    ):
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PROMPT_HASH_INVALID"
        )
    if row.get("prompt_override_authorized") is not True:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PROMPT_OVERRIDE_NOT_AUTHORIZED"
        )

    if row.get("person_generation_override_authorized") is not True:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PERSON_GENERATION_OVERRIDE_NOT_AUTHORIZED"
        )
    historical_pg = str(row.get("historical_person_generation") or "")
    replacement_pg = str(row.get("replacement_person_generation") or "")
    if historical_pg not in _ALLOWED_PERSON_GENERATION:
        raise TerminalProviderReplacementAuthorizationError(
            "HISTORICAL_PERSON_GENERATION_INVALID"
        )
    if replacement_pg not in _ALLOWED_PERSON_GENERATION:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PERSON_GENERATION_INVALID"
        )
    return row


def terminal_replacement_authorization_for_request(
    repo_root: Path,
    episode_id: str,
    request_id: str,
) -> dict[str, Any] | None:
    path = authorization_path(repo_root, episode_id)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_FILE_INVALID"
        ) from exc
    if not isinstance(value, Mapping):
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_OBJECT_REQUIRED"
        )
    return _validate_authorization(
        value,
        episode_id=episode_id,
        request_id=request_id,
    )


def terminal_replacement_authorization_matches_reconciliation(
    authorization: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
) -> bool:
    try:
        return (
            str(authorization.get("reconciliation_receipt_id") or "")
            == str(reconciliation.get("receipt_id") or "")
            and str(authorization.get("reconciliation_receipt_sha256") or "")
            == str(reconciliation.get("receipt_sha256") or "")
            and str(authorization.get("historical_attempt_id") or "")
            == str(reconciliation.get("historical_attempt_id") or "")
            and str(authorization.get("provider_request_id") or "")
            == str(reconciliation.get("provider_request_id") or "")
            and str(authorization.get("media_unit_id") or "")
            == str(reconciliation.get("media_unit_id") or "")
            and str(authorization.get("provider") or "")
            == str(reconciliation.get("provider") or "")
            and str(authorization.get("model") or "")
            == str(reconciliation.get("model") or "")
            and str(authorization.get("provider_error_code") or "")
            == str(reconciliation.get("provider_error_code") or "")
            and str(reconciliation.get("original_charge_status") or "")
            == "PROVEN_NOT_CHARGED"
            and reconciliation.get("terminal_provider_rejection") is True
            and reconciliation.get("safe_to_reauthorize") is True
            and reconciliation.get("billable_output_detected") is False
            and reconciliation.get("historical_attempt_reusable") is False
            and reconciliation.get(
                "new_attempt_required_for_future_submission"
            )
            is True
            and reconciliation.get("automatic_paid_retry") is False
            and reconciliation.get("automatic_paid_resubmission") is False
            and abs(
                float(authorization.get("planned_cost_usd") or 0.0)
                - float(
                    reconciliation.get("planned_future_request_cost_usd")
                    or 0.0
                )
            )
            <= 1e-9
        )
    except (TypeError, ValueError):
        return False


def apply_terminal_replacement_prompt(
    task: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(task, Mapping):
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_TASK_MAPPING_REQUIRED"
        )
    result = copy.deepcopy(dict(task))

    original_prompt = str(result.get("positivePrompt") or "")
    expected_prompt_sha = str(
        authorization.get("historical_positive_prompt_sha256") or ""
    )
    if not original_prompt or _text_sha256(original_prompt) != expected_prompt_sha:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_SOURCE_PROMPT_CHANGED_FAIL_CLOSED"
        )

    observed_pg = _nested_person_generation(result)
    expected_pg = str(
        authorization.get("historical_person_generation") or ""
    )
    if observed_pg != expected_pg:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_SOURCE_PERSON_GENERATION_CHANGED_FAIL_CLOSED:"
            + observed_pg
        )

    replacement_prompt = str(
        authorization.get("replacement_positive_prompt") or ""
    )
    if _text_sha256(replacement_prompt) != str(
        authorization.get("replacement_positive_prompt_sha256") or ""
    ):
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PROMPT_HASH_INVALID"
        )
    replacement_pg = str(
        authorization.get("replacement_person_generation") or ""
    )
    if replacement_pg not in _ALLOWED_PERSON_GENERATION:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PERSON_GENERATION_INVALID"
        )

    original_task_uuid = str(result.get("taskUUID") or "")
    result["positivePrompt"] = replacement_prompt

    provider_settings = result.get("providerSettings")
    if not isinstance(provider_settings, Mapping):
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PROVIDER_SETTINGS_REQUIRED"
        )
    google = provider_settings.get("google")
    if not isinstance(google, Mapping):
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_GOOGLE_PROVIDER_SETTINGS_REQUIRED"
        )

    new_provider_settings = dict(provider_settings)
    new_google = dict(google)
    new_google["personGeneration"] = replacement_pg
    new_provider_settings["google"] = new_google
    result["providerSettings"] = new_provider_settings

    if str(result.get("taskUUID") or "") != original_task_uuid:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_TASK_UUID_CHANGED_BY_OVERRIDE"
        )
    if _nested_person_generation(result) != replacement_pg:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_PERSON_GENERATION_OVERRIDE_FAILED"
        )
    return result


def _validated_consumptions(
    repo_root: Path,
    episode_id: str,
) -> list[dict[str, Any]]:
    rows = _read_jsonl(consumption_path(repo_root, episode_id))
    valid: list[dict[str, Any]] = []
    for row in rows:
        if row.get("schema_version") != CONSUMPTION_SCHEMA_VERSION:
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_CONSUMPTION_SCHEMA_INVALID"
            )
        if str(row.get("episode_id") or "") != str(episode_id):
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_CONSUMPTION_EPISODE_MISMATCH"
            )
        expected = _canonical_sha256(_unsigned_consumption(row))
        if str(row.get("consumption_sha256") or "") != expected:
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_CONSUMPTION_HASH_INVALID"
            )
        if row.get("automatic_paid_retry") is not False:
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_CONSUMPTION_AUTOMATIC_RETRY_INVALID"
            )
        if row.get("automatic_paid_resubmission") is not False:
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_CONSUMPTION_AUTOMATIC_RESUBMISSION_INVALID"
            )
        valid.append(row)
    return valid


def consumption_for_authorization(
    repo_root: Path,
    episode_id: str,
    authorization_id: str,
) -> dict[str, Any] | None:
    matches = [
        row
        for row in _validated_consumptions(repo_root, episode_id)
        if str(row.get("authorization_id") or "") == str(authorization_id)
    ]
    if not matches:
        return None
    attempts = {
        str(row.get("replacement_attempt_id") or "")
        for row in matches
    }
    if len(attempts) != 1:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_CONSUMED_BY_MULTIPLE_ATTEMPTS"
        )
    return matches[-1]


def consume_terminal_replacement_authorization(
    repo_root: Path,
    episode_id: str,
    authorization: Mapping[str, Any],
    *,
    attempt_id: str,
) -> dict[str, Any]:
    auth = _validate_authorization(
        authorization,
        episode_id=episode_id,
        request_id=str(
            authorization.get("provider_request_id")
            or authorization.get("media_unit_id")
            or ""
        ),
    )
    expected_attempt = str(auth.get("replacement_attempt_id") or "")
    if str(attempt_id) != expected_attempt:
        raise TerminalProviderReplacementAuthorizationError(
            "REPLACEMENT_AUTHORIZATION_ATTEMPT_MISMATCH"
        )

    path = consumption_path(repo_root, episode_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")

    with _LOCK:
        try:
            fd = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as exc:
            raise TerminalProviderReplacementAuthorizationError(
                "REPLACEMENT_AUTHORIZATION_CONSUMPTION_LOCKED"
            ) from exc

        try:
            os.write(fd, (str(os.getpid()) + "\n").encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)

        try:
            rows = _validated_consumptions(repo_root, episode_id)
            same = [
                row
                for row in rows
                if str(row.get("authorization_id") or "")
                == str(auth.get("authorization_id") or "")
            ]
            if same:
                attempts = {
                    str(row.get("replacement_attempt_id") or "")
                    for row in same
                }
                if attempts != {expected_attempt}:
                    raise TerminalProviderReplacementAuthorizationError(
                        "REPLACEMENT_AUTHORIZATION_ALREADY_CONSUMED_OTHER_ATTEMPT"
                    )
                return same[-1]

            unsigned: dict[str, Any] = {
                "schema_version": CONSUMPTION_SCHEMA_VERSION,
                "consumption_id": str(uuid.uuid4()),
                "episode_id": str(episode_id),
                "stage": "PROVIDER_EXECUTION",
                "event": (
                    "EXPLICIT_TERMINAL_REPLACEMENT_AUTHORIZATION_CONSUMED"
                ),
                "timestamp_utc": datetime.now(timezone.utc).isoformat().replace(
                    "+00:00", "Z"
                ),
                "authorization_id": str(auth.get("authorization_id") or ""),
                "authorization_sha256": str(
                    auth.get("authorization_sha256") or ""
                ),
                "provider_request_id": str(
                    auth.get("provider_request_id") or ""
                ),
                "media_unit_id": str(auth.get("media_unit_id") or ""),
                "historical_attempt_id": str(
                    auth.get("historical_attempt_id") or ""
                ),
                "replacement_attempt_id": expected_attempt,
                "maximum_provider_requests": 1,
                "planned_cost_usd": float(
                    auth.get("planned_cost_usd") or 0.0
                ),
                "maximum_cost_usd": float(
                    auth.get("maximum_cost_usd") or 0.0
                ),
                "automatic_paid_retry": False,
                "automatic_paid_resubmission": False,
                "provider_submission_performed_by_consumption": False,
            }
            unsigned["consumption_sha256"] = _canonical_sha256(unsigned)
            payload = _canonical_json_bytes(unsigned) + b"\n"
            with path.open("ab") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            return unsigned
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


__all__ = [
    "TerminalProviderReplacementAuthorizationError",
    "apply_terminal_replacement_prompt",
    "authorization_path",
    "consume_terminal_replacement_authorization",
    "consumption_for_authorization",
    "consumption_path",
    "terminal_replacement_authorization_for_request",
    "terminal_replacement_authorization_matches_reconciliation",
]
