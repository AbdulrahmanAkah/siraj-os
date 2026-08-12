"""Provider-aware one-shot Luna transport for SIRAJ V5.

No fixed sleeps. No SIRAJ max-output cap. No automatic retry.
Rate-limit headers and 429 cooldown are persisted and honored adaptively.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_local_resource_guard_v5_2 import (
    activate_local_resource_guard,
)

LOCAL_RESOURCE_GUARD_STATE = activate_local_resource_guard()

from src.application.siraj_luna_runtime_policy_v5 import (
    apply_unbounded_request_policy,
)
from src.application.siraj_luna_iconic_cinematic_brain_v5_1 import (
    apply_iconic_cinematic_brain,
    detect_stage,
)

RESPONSES_URL = "https://api.openai.com/v1/responses"
REQUEST_TIMEOUT_SECONDS = 900
RATE_STATE_REL = Path("projects/_series/luna-provider-rate-state-v5.json")


class LunaAdaptiveTransportError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def _load_windows_credential(target: str) -> str:
    if os.name != "nt":
        return ""

    CRED_TYPE_GENERIC = 1

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    PCREDENTIALW = ctypes.POINTER(CREDENTIALW)
    pcred = PCREDENTIALW()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    cred_read = advapi32.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(PCREDENTIALW),
    ]
    cred_read.restype = wintypes.BOOL

    cred_free = advapi32.CredFree
    cred_free.argtypes = [ctypes.c_void_p]
    cred_free.restype = None

    if not cred_read(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
        return ""

    try:
        cred = pcred.contents
        raw = ctypes.string_at(
            cred.CredentialBlob,
            int(cred.CredentialBlobSize),
        )
        try:
            value = raw.decode("utf-16-le").rstrip("\x00").strip()
        except UnicodeDecodeError:
            value = raw.decode("utf-8").rstrip("\x00").strip()
        return value
    finally:
        cred_free(pcred)


def load_openai_api_key() -> tuple[str, str]:
    env = os.environ.get("OPENAI_API_KEY", "").strip()
    if env:
        return env, "ENVIRONMENT"

    value = _load_windows_credential("SIRAJ/OPENAI_API_KEY")
    if value:
        return value, "WINDOWS_CREDENTIAL_MANAGER"

    raise LunaAdaptiveTransportError("OPENAI_API_KEY_NOT_AVAILABLE")


def _header_dict(headers: Any) -> dict[str, str]:
    names = (
        "x-request-id",
        "x-ratelimit-limit-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "retry-after",
    )
    result: dict[str, str] = {}
    for name in names:
        try:
            value = headers.get(name)
        except Exception:
            value = None
        if value is not None:
            result[name] = str(value)
    return result


_DURATION_RE = re.compile(
    r"(?:(?P<h>\d+(?:\.\d+)?)h)?"
    r"(?:(?P<m>\d+(?:\.\d+)?)m)?"
    r"(?:(?P<s>\d+(?:\.\d+)?)s)?"
)


def _duration_seconds(value: str) -> float:
    raw = str(value or "").strip().lower()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    match = _DURATION_RE.fullmatch(raw)
    if not match:
        return 0.0
    return (
        float(match.group("h") or 0) * 3600
        + float(match.group("m") or 0) * 60
        + float(match.group("s") or 0)
    )


def _retry_seconds_from_body(body: str) -> float:
    match = re.search(
        r"Please try again in\s+([0-9]+(?:\.[0-9]+)?)s",
        body,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else 0.0


def _honor_persisted_provider_cooldown(rate_state_path: Path) -> None:
    state = _read_json(rate_state_path)
    not_before = float(state.get("not_before_epoch", 0) or 0)
    remaining = not_before - time.time()
    if remaining > 0:
        print(
            "LUNA_PROVIDER_COOLDOWN_WAIT_SECONDS="
            + str(round(remaining, 3))
        )
        time.sleep(remaining)


def _persist_success_rate_state(
    path: Path,
    headers: Mapping[str, str],
) -> None:
    reset_tokens = _duration_seconds(
        headers.get("x-ratelimit-reset-tokens", "")
    )
    remaining_tokens = headers.get("x-ratelimit-remaining-tokens")
    limit_tokens = headers.get("x-ratelimit-limit-tokens")

    # We do not invent a fixed delay. Persist provider state only.
    _atomic_write(
        path,
        {
            "schema_version": "siraj-luna-provider-rate-state-v5",
            "status": "PROVIDER_HEADERS_OBSERVED",
            "limit_tokens": limit_tokens,
            "remaining_tokens": remaining_tokens,
            "reset_tokens_seconds": reset_tokens,
            "not_before_epoch": 0,
            "headers": dict(headers),
            "updated_at_utc": _now(),
        },
    )


def _persist_429_rate_state(
    path: Path,
    headers: Mapping[str, str],
    body: str,
) -> float:
    candidates = [
        _duration_seconds(headers.get("retry-after", "")),
        _duration_seconds(
            headers.get("x-ratelimit-reset-tokens", "")
        ),
        _retry_seconds_from_body(body),
    ]
    wait_seconds = max(candidates)
    not_before = time.time() + wait_seconds if wait_seconds > 0 else 0
    _atomic_write(
        path,
        {
            "schema_version": "siraj-luna-provider-rate-state-v5",
            "status": "RATE_LIMITED",
            "wait_seconds_from_provider": wait_seconds,
            "not_before_epoch": not_before,
            "headers": dict(headers),
            "updated_at_utc": _now(),
        },
    )
    return wait_seconds


def post_luna_once(
    repo: Path,
    request_payload: Mapping[str, Any],
    *,
    client_request_id: str | None = None,
) -> dict[str, Any]:
    """Submit exactly once. Never retries automatically."""
    repo = Path(repo).resolve()
    rate_state_path = repo / RATE_STATE_REL
    _honor_persisted_provider_cooldown(rate_state_path)

    api_key, key_source = load_openai_api_key()
    payload = apply_unbounded_request_policy(request_payload)
    payload = apply_iconic_cinematic_brain(payload)
    stage = detect_stage(payload)
    print("LOCAL_RESOURCE_GUARD=ACTIVE")
    print("LOCAL_PROCESS_PRIORITY=BELOW_NORMAL")
    print("LUNA_REASONING_EFFORT=MAX")
    print("LUNA_REASONING_MODE=PRO")
    print("LUNA_ICONIC_CINEMATIC_BRAIN=ACTIVE")
    print("LUNA_BRAIN_STAGE=" + stage)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    cid = client_request_id or str(uuid.uuid4())
    request = urllib.request.Request(
        RESPONSES_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Client-Request-Id": cid,
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            raw = response.read()
            headers = _header_dict(response.headers)
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise LunaAdaptiveTransportError(
                    "OPENAI_RESPONSE_OBJECT_REQUIRED"
                )
            value["_siraj_http_meta"] = {
                "client_request_id": cid,
                "key_source": key_source,
                "headers": headers,
            }
            _persist_success_rate_state(rate_state_path, headers)
            return value

    except urllib.error.HTTPError as exc:
        raw = exc.read()
        body_text = raw.decode("utf-8", errors="replace")
        headers = _header_dict(exc.headers)
        if exc.code == 429:
            wait_seconds = _persist_429_rate_state(
                rate_state_path,
                headers,
                body_text,
            )
            raise LunaAdaptiveTransportError(
                "OPENAI_429_NO_AUTO_RETRY:"
                f"provider_wait_seconds={wait_seconds}:"
                + body_text[:1400]
            ) from exc

        raise LunaAdaptiveTransportError(
            f"OPENAI_HTTP_{exc.code}:"
            + body_text[:1400]
        ) from exc
