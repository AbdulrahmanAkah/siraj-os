from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "siraj-provider-execution-remaining-stage-authorization-v1"
AUTH_FILENAME = "remaining-stage-authorization-v1.json"


class RemainingStageAuthorizationError(RuntimeError):
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


def _unsigned_authorization(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    row = dict(value)
    row.pop("authorization_sha256", None)
    return row


def authorization_path(
    repo_root: Path,
    episode_id: str,
) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / str(episode_id)
        / "orchestration"
        / "provider-execution-v1"
        / AUTH_FILENAME
    )


def _validate_authorization(
    value: Mapping[str, Any],
    *,
    episode_id: str,
) -> dict[str, Any]:
    row = dict(value)
    if row.get("schema_version") != SCHEMA_VERSION:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZATION_SCHEMA_INVALID"
        )
    if str(row.get("episode_id") or "") != str(episode_id):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZATION_EPISODE_MISMATCH"
        )
    if row.get("stage") != "PROVIDER_EXECUTION":
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZATION_STAGE_MISMATCH"
        )
    if row.get("status") != "AUTHORIZED":
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZATION_STATUS_INVALID"
        )

    expected_hash = _canonical_sha256(
        _unsigned_authorization(row)
    )
    if str(row.get("authorization_sha256") or "") != expected_hash:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZATION_HASH_INVALID"
        )

    authorization_id = str(row.get("authorization_id") or "")
    if not authorization_id:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZATION_ID_REQUIRED"
        )

    if row.get("skip_durable_completed_units") is not True:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_SKIP_COMPLETED_REQUIRED"
        )
    if row.get("stop_on_first_unresolved_or_failed_attempt") is not True:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_STOP_ON_FAILURE_REQUIRED"
        )
    if row.get("automatic_paid_retry") is not False:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTOMATIC_RETRY_FORBIDDEN"
        )
    if row.get("automatic_paid_resubmission") is not False:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTOMATIC_RESUBMISSION_FORBIDDEN"
        )

    maximum_requests = int(
        row.get("maximum_provider_submissions") or 0
    )
    authorized_count = int(
        row.get("authorized_remaining_units_count") or 0
    )
    if maximum_requests <= 0 or maximum_requests != authorized_count:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_REQUEST_COUNT_INVALID"
        )

    planned_total = float(
        row.get("authorized_planned_total_usd") or -1.0
    )
    maximum_total = float(
        row.get("maximum_total_usd") or -1.0
    )
    if (
        planned_total < 0
        or maximum_total < 0
        or planned_total > maximum_total + 1e-9
    ):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_COST_CAP_INVALID"
        )

    units = row.get("authorized_units")
    if not isinstance(units, list):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZED_UNITS_REQUIRED"
        )
    if len(units) != authorized_count:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZED_UNIT_COUNT_MISMATCH"
        )

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    cost_sum = 0.0
    for raw in units:
        if not isinstance(raw, Mapping):
            raise RemainingStageAuthorizationError(
                "REMAINING_STAGE_AUTHORIZED_UNIT_OBJECT_REQUIRED"
            )
        unit_id = str(raw.get("unit_id") or "")
        if not unit_id or unit_id in seen:
            raise RemainingStageAuthorizationError(
                "REMAINING_STAGE_AUTHORIZED_UNIT_ID_INVALID:"
                + unit_id
            )
        seen.add(unit_id)
        cost = raw.get("expected_cost_usd")
        if (
            not isinstance(cost, (int, float))
            or isinstance(cost, bool)
        ):
            raise RemainingStageAuthorizationError(
                "REMAINING_STAGE_AUTHORIZED_UNIT_COST_INVALID:"
                + unit_id
            )
        cost_sum += float(cost)
        normalized.append(dict(raw))

    if abs(cost_sum - planned_total) > 1e-6:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZED_COST_SUM_MISMATCH"
        )

    expected_units_sha = _canonical_sha256(
        sorted(
            normalized,
            key=lambda item: str(item.get("unit_id") or ""),
        )
    )
    if str(row.get("authorized_units_sha256") or "") != expected_units_sha:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZED_UNITS_HASH_INVALID"
        )

    baseline = row.get("baseline_durable_completed")
    if not isinstance(baseline, Mapping):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_BASELINE_COMPLETED_REQUIRED"
        )
    if int(
        row.get("baseline_durable_completed_count") or -1
    ) != len(baseline):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_BASELINE_COMPLETED_COUNT_MISMATCH"
        )

    if not str(row.get("binding_sha256") or ""):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_BINDING_HASH_REQUIRED"
        )
    binding = row.get("binding")
    if not isinstance(binding, Mapping):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_BINDING_REQUIRED"
        )
    if _canonical_sha256(dict(binding)) != str(
        row.get("binding_sha256") or ""
    ):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_BINDING_HASH_INVALID"
        )

    if not str(row.get("prior_scope_pause_receipt_sha256") or ""):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_PRIOR_SCOPE_PAUSE_HASH_REQUIRED"
        )

    return row


def remaining_stage_authorization_for_episode(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any] | None:
    path = authorization_path(repo_root, episode_id)
    if not path.is_file():
        return None
    try:
        value = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZATION_FILE_INVALID"
        ) from exc
    if not isinstance(value, Mapping):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_AUTHORIZATION_OBJECT_REQUIRED"
        )
    return _validate_authorization(
        value,
        episode_id=episode_id,
    )


def validate_remaining_stage_authorization_current(
    authorization: Mapping[str, Any],
    *,
    episode_id: str,
    binding: Mapping[str, Any],
    provider_units: list[Mapping[str, Any]],
    durable_completed: Mapping[str, str],
    prior_scope_pause: Mapping[str, Any],
) -> dict[str, Any]:
    auth = _validate_authorization(
        authorization,
        episode_id=episode_id,
    )

    if _canonical_sha256(dict(binding)) != str(
        auth.get("binding_sha256") or ""
    ):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_CURRENT_BINDING_CHANGED"
        )

    prior_pause_sha = str(
        prior_scope_pause.get("receipt_sha256") or ""
    )
    if prior_pause_sha != str(
        auth.get("prior_scope_pause_receipt_sha256") or ""
    ):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_PRIOR_SCOPE_PAUSE_CHANGED"
        )
    if str(
        prior_scope_pause.get("scope_authorization_id") or ""
    ) != str(
        auth.get("prior_scope_pause_authorization_id") or ""
    ):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_PRIOR_SCOPE_AUTHORIZATION_CHANGED"
        )
    if str(
        prior_scope_pause.get("scope_completed_unit_id") or ""
    ) != str(
        auth.get("prior_scope_completed_unit_id") or ""
    ):
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_PRIOR_SCOPE_COMPLETED_UNIT_CHANGED"
        )
    if prior_scope_pause.get("remaining_stage_not_authorized") is not True:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_PRIOR_SCOPE_FLAG_INVALID"
        )

    current_units: dict[str, dict[str, Any]] = {}
    for raw in provider_units:
        unit = dict(raw)
        unit_id = str(
            unit.get("request_id")
            or unit.get("unit_id")
            or ""
        )
        if not unit_id or unit_id in current_units:
            raise RemainingStageAuthorizationError(
                "REMAINING_STAGE_CURRENT_UNIT_ID_INVALID:"
                + unit_id
            )
        current_units[unit_id] = unit

    authorized_entries = {
        str(item.get("unit_id") or ""): dict(item)
        for item in auth["authorized_units"]
    }
    baseline = {
        str(key): str(value)
        for key, value in dict(
            auth["baseline_durable_completed"]
        ).items()
    }
    durable = {
        str(key): str(value)
        for key, value in dict(durable_completed).items()
    }

    expected_total_ids = set(baseline) | set(authorized_entries)
    if set(current_units) != expected_total_ids:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_CURRENT_PROVIDER_UNIVERSE_CHANGED"
        )

    for unit_id, attempt_id in baseline.items():
        if durable.get(unit_id) != attempt_id:
            raise RemainingStageAuthorizationError(
                "REMAINING_STAGE_BASELINE_COMPLETED_CHANGED:"
                + unit_id
            )

    unexpected_durable = set(durable) - expected_total_ids
    if unexpected_durable:
        raise RemainingStageAuthorizationError(
            "REMAINING_STAGE_UNEXPECTED_DURABLE_UNIT:"
            + ",".join(sorted(unexpected_durable))
        )

    for unit_id, entry in authorized_entries.items():
        current = current_units.get(unit_id)
        if current is None:
            raise RemainingStageAuthorizationError(
                "REMAINING_STAGE_AUTHORIZED_UNIT_MISSING:"
                + unit_id
            )
        checks = {
            "provider": str(current.get("provider") or ""),
            "model": str(current.get("model") or ""),
            "payload_sha256": str(
                current.get("payload_sha256") or ""
            ),
        }
        for key, observed in checks.items():
            if observed != str(entry.get(key) or ""):
                raise RemainingStageAuthorizationError(
                    "REMAINING_STAGE_AUTHORIZED_UNIT_CHANGED:"
                    + unit_id
                    + ":"
                    + key
                )
        current_cost = current.get("expected_cost_usd")
        if (
            not isinstance(current_cost, (int, float))
            or isinstance(current_cost, bool)
            or abs(
                float(current_cost)
                - float(entry.get("expected_cost_usd") or 0.0)
            )
            > 1e-9
        ):
            raise RemainingStageAuthorizationError(
                "REMAINING_STAGE_AUTHORIZED_UNIT_COST_CHANGED:"
                + unit_id
            )

    current_remaining = sorted(
        unit_id
        for unit_id in authorized_entries
        if unit_id not in durable
    )
    return {
        "authorization_id": str(
            auth.get("authorization_id") or ""
        ),
        "authorized_unit_ids": sorted(authorized_entries),
        "authorized_unit_entries": authorized_entries,
        "baseline_completed_count": len(baseline),
        "current_durable_completed_count": len(durable),
        "current_remaining_unit_ids": current_remaining,
        "current_remaining_count": len(current_remaining),
        "maximum_provider_submissions": int(
            auth["maximum_provider_submissions"]
        ),
        "maximum_total_usd": float(auth["maximum_total_usd"]),
        "authorized_planned_total_usd": float(
            auth["authorized_planned_total_usd"]
        ),
    }


__all__ = [
    "RemainingStageAuthorizationError",
    "authorization_path",
    "remaining_stage_authorization_for_episode",
    "validate_remaining_stage_authorization_current",
]
