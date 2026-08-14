"""Hash-bound, single-use authorization for local Shorts rendering.

This module is deliberately provider-free.  It separates the ability to
prepare a render plan from the ability to consume one explicit Desktop
authorization.  Synthetic tests use the same envelope and validator but are
never allowed to render a real user source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid
from typing import Any, Mapping, Sequence

from src.application.artifact_provenance_v1 import atomic_write_json


SCHEMA_VERSION = "siraj-shorts-local-render-authorization-v1"
REAL_MODE = "REAL_EPISODE_LOCAL_RENDER"
TEST_MODE = "SYNTHETIC_TEST_EXECUTION"
ALLOWED_REAL_ORIGIN = "SIRAJ_DESKTOP"
ALLOWED_TEST_ORIGIN = "TEST_HARNESS"
FORBIDDEN_ORIGINS = frozenset({"TERMINAL", "CLI", "RECOVERY", "PYTHON", "UNKNOWN"})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_CONSUMED_IDS: set[str] = set()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _lock_for(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def _require_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", f"{field}:SHA256_REQUIRED")
    return value


def _require_nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", f"{field}:REQUIRED")
    return value.strip()


def _desktop_runtime_active() -> bool:
    """Require a live Qt Desktop process for real-mode authorization."""

    try:
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() is not None
    except (ImportError, RuntimeError):
        return False


class RenderAuthorizationError(RuntimeError):
    """Raised when a local render envelope is absent, stale, or consumed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


@dataclass(frozen=True, slots=True)
class ShortsLocalRenderAuthorization:
    authorization_id: str
    episode_id: str
    source_episode_sha256: str
    short_plan_sha256: str
    profile_sha256: str
    constitution_bundle_sha256: str
    execution_origin: str
    execution_mode: str
    authorized_output_directory: str
    authorized_short_ids: tuple[str, ...]
    issued_at: str
    human_action_nonce: str
    explicit_human_click: bool
    consumed: bool = False
    consumed_at: str | None = None
    authorization_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["authorized_short_ids"] = list(self.authorized_short_ids)
        return value

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ShortsLocalRenderAuthorization":
        if not isinstance(value, Mapping):
            raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "OBJECT_REQUIRED")
        try:
            short_ids = value["authorized_short_ids"]
            if isinstance(short_ids, str) or not isinstance(short_ids, Sequence) or not short_ids:
                raise TypeError
            parsed_short_ids = tuple(_require_nonempty(item, "authorized_short_ids") for item in short_ids)
            result = cls(
                authorization_id=_require_nonempty(value.get("authorization_id"), "authorization_id"),
                episode_id=_require_nonempty(value.get("episode_id"), "episode_id"),
                source_episode_sha256=_require_hash(value.get("source_episode_sha256"), "source_episode_sha256"),
                short_plan_sha256=_require_hash(value.get("short_plan_sha256"), "short_plan_sha256"),
                profile_sha256=_require_hash(value.get("profile_sha256"), "profile_sha256"),
                constitution_bundle_sha256=_require_hash(value.get("constitution_bundle_sha256"), "constitution_bundle_sha256"),
                execution_origin=_require_nonempty(value.get("execution_origin"), "execution_origin").upper(),
                execution_mode=_require_nonempty(value.get("execution_mode"), "execution_mode").upper(),
                authorized_output_directory=_require_nonempty(value.get("authorized_output_directory"), "authorized_output_directory"),
                authorized_short_ids=parsed_short_ids,
                issued_at=_require_nonempty(value.get("issued_at"), "issued_at"),
                human_action_nonce=_require_nonempty(value.get("human_action_nonce"), "human_action_nonce"),
                explicit_human_click=value.get("explicit_human_click") is True,
                consumed=value.get("consumed") is True,
                consumed_at=(None if value.get("consumed_at") is None else str(value.get("consumed_at"))),
                authorization_path=(None if value.get("authorization_path") is None else str(value.get("authorization_path"))),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "FIELDS_INVALID") from exc
        validate_authorization(result)
        return result


def validate_authorization(
    authorization: ShortsLocalRenderAuthorization,
    *,
    expected_episode_id: str | None = None,
    expected_source_sha256: str | None = None,
    expected_plan_sha256: str | None = None,
    expected_profile_sha256: str | None = None,
    expected_constitution_sha256: str | None = None,
    expected_short_id: str | None = None,
    expected_output_directory: Path | None = None,
) -> None:
    if authorization.execution_origin in FORBIDDEN_ORIGINS:
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "EXECUTION_ORIGIN_FORBIDDEN")
    if authorization.execution_mode == REAL_MODE and authorization.execution_origin != ALLOWED_REAL_ORIGIN:
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "REAL_MODE_REQUIRES_SIRAJ_DESKTOP")
    if authorization.execution_mode == REAL_MODE and not _desktop_runtime_active():
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "DESKTOP_RUNTIME_REQUIRED")
    if authorization.execution_mode == TEST_MODE and authorization.execution_origin != ALLOWED_TEST_ORIGIN:
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "TEST_MODE_REQUIRES_TEST_HARNESS")
    if authorization.execution_mode not in {REAL_MODE, TEST_MODE}:
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "EXECUTION_MODE_INVALID")
    if not authorization.explicit_human_click:
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "EXPLICIT_HUMAN_CLICK_REQUIRED")
    if len(set(authorization.authorized_short_ids)) != len(authorization.authorized_short_ids):
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "DUPLICATE_SHORT_ID")
    checks = (
        (expected_episode_id, authorization.episode_id, "EPISODE_HASH_BINDING_MISMATCH"),
        (expected_source_sha256, authorization.source_episode_sha256, "SOURCE_HASH_BINDING_MISMATCH"),
        (expected_plan_sha256, authorization.short_plan_sha256, "PLAN_HASH_BINDING_MISMATCH"),
        (expected_profile_sha256, authorization.profile_sha256, "PROFILE_HASH_BINDING_MISMATCH"),
        (expected_constitution_sha256, authorization.constitution_bundle_sha256, "CONSTITUTION_HASH_BINDING_MISMATCH"),
    )
    for expected, actual, detail in checks:
        if expected is not None and expected != actual:
            raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_STALE", detail)
    if expected_short_id is not None and expected_short_id not in authorization.authorized_short_ids:
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "SHORT_ID_NOT_AUTHORIZED")
    if expected_output_directory is not None:
        expected = Path(expected_output_directory).resolve()
        authorized = Path(authorization.authorized_output_directory).resolve()
        if expected != authorized:
            raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_INVALID", "OUTPUT_DIRECTORY_NOT_AUTHORIZED")
    if authorization.consumed:
        raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_CONSUMED", authorization.authorization_id)


def issue_authorization(
    *,
    episode_id: str,
    source_episode_sha256: str,
    short_plan_sha256: str,
    profile_sha256: str,
    constitution_bundle_sha256: str,
    execution_origin: str,
    execution_mode: str,
    authorized_output_directory: Path,
    authorized_short_ids: Sequence[str],
    explicit_human_click: bool,
    authorization_path: Path | None = None,
) -> ShortsLocalRenderAuthorization:
    origin = _require_nonempty(execution_origin, "execution_origin").upper()
    mode = _require_nonempty(execution_mode, "execution_mode").upper()
    result = ShortsLocalRenderAuthorization(
        authorization_id="SHORT-AUTH-" + uuid.uuid4().hex,
        episode_id=_require_nonempty(episode_id, "episode_id"),
        source_episode_sha256=_require_hash(source_episode_sha256, "source_episode_sha256"),
        short_plan_sha256=_require_hash(short_plan_sha256, "short_plan_sha256"),
        profile_sha256=_require_hash(profile_sha256, "profile_sha256"),
        constitution_bundle_sha256=_require_hash(constitution_bundle_sha256, "constitution_bundle_sha256"),
        execution_origin=origin,
        execution_mode=mode,
        authorized_output_directory=str(Path(authorized_output_directory).resolve()),
        authorized_short_ids=tuple(_require_nonempty(item, "authorized_short_ids") for item in authorized_short_ids),
        issued_at=utc_now(),
        human_action_nonce=uuid.uuid4().hex,
        explicit_human_click=explicit_human_click,
        authorization_path=(None if authorization_path is None else str(Path(authorization_path).resolve())),
    )
    validate_authorization(result)
    if authorization_path is not None:
        atomic_write_json(Path(authorization_path), result.to_dict(), preserve_previous=False)
    return result


def consume_authorization(
    authorization: ShortsLocalRenderAuthorization | Mapping[str, Any],
    *,
    expected_episode_id: str,
    expected_source_sha256: str,
    expected_plan_sha256: str,
    expected_profile_sha256: str,
    expected_constitution_sha256: str,
    expected_short_id: str,
    expected_output_directory: Path,
) -> ShortsLocalRenderAuthorization:
    current = authorization if isinstance(authorization, ShortsLocalRenderAuthorization) else ShortsLocalRenderAuthorization.from_mapping(authorization)
    validate_authorization(
        current,
        expected_episode_id=expected_episode_id,
        expected_source_sha256=expected_source_sha256,
        expected_plan_sha256=expected_plan_sha256,
        expected_profile_sha256=expected_profile_sha256,
        expected_constitution_sha256=expected_constitution_sha256,
        expected_short_id=expected_short_id,
        expected_output_directory=expected_output_directory,
    )
    path = Path(current.authorization_path).resolve() if current.authorization_path else None
    lock_key = str(path or current.authorization_id)
    with _lock_for(lock_key):
        if current.authorization_id in _CONSUMED_IDS:
            raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_CONSUMED", current.authorization_id)
        if path is not None and path.is_file():
            persisted = ShortsLocalRenderAuthorization.from_mapping(json.loads(path.read_text(encoding="utf-8")))
            if persisted.authorization_id != current.authorization_id:
                raise RenderAuthorizationError("SHORT_RENDER_AUTHORIZATION_STALE", "AUTHORIZATION_ID_CHANGED")
            current = persisted
            validate_authorization(
                current,
                expected_episode_id=expected_episode_id,
                expected_source_sha256=expected_source_sha256,
                expected_plan_sha256=expected_plan_sha256,
                expected_profile_sha256=expected_profile_sha256,
                expected_constitution_sha256=expected_constitution_sha256,
                expected_short_id=expected_short_id,
                expected_output_directory=expected_output_directory,
            )
        consumed = ShortsLocalRenderAuthorization(
            **{
                **current.to_dict(),
                "authorized_short_ids": tuple(current.authorized_short_ids),
                "consumed": True,
                "consumed_at": utc_now(),
            }
        )
        if path is not None:
            atomic_write_json(path, consumed.to_dict(), preserve_previous=True)
        _CONSUMED_IDS.add(current.authorization_id)
        return consumed


def authorization_fingerprint(authorization: ShortsLocalRenderAuthorization) -> str:
    return _sha256(authorization.to_dict())


__all__ = [
    "SCHEMA_VERSION",
    "REAL_MODE",
    "TEST_MODE",
    "ShortsLocalRenderAuthorization",
    "RenderAuthorizationError",
    "issue_authorization",
    "consume_authorization",
    "validate_authorization",
    "authorization_fingerprint",
]
