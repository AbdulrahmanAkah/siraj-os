"""SIRAJ V6.3 Luna transport for future-episode upstream stages.

Properties:
- model is resolved from SIRAJ_LUNA_MODEL or the existing SIRAJ Luna model;
- no assistant-authored call-count, token-output, or monetary cap;
- every paid call requires an immutable explicit authorization;
- an attempt lock is persisted before network;
- the raw provider response is persisted before semantic parsing;
- provider/network failure never triggers an automatic paid retry;
- usage/accounting is append-only and advisory, never an execution cap.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
import urllib.error
import urllib.request
import uuid

from src.application.provider_credentials_v1 import read_openai_api_key
# SIRAJ_LUNA_TRUE_TELEMETRY_V6_6_R9
from src.application.siraj_live_telemetry_v6_6_r9 import emit_event
from src.application.artifact_provenance_v1 import (
    atomic_write_json,
    is_currently_valid,
    write_new_json,
)
from src.application.paid_operation_gateway import (
    PaidOperationRequest,
    execute_json as execute_paid_json,
    http_json_transport,
)
from src.application.paid_operation_identity_v1 import (
    build_paid_operation_identity,
    provider_payload_sha256,
)
from src.application.provider_model_contracts import (
    CONTRACT_VERSION as PROVIDER_CONTRACT_VERSION,
    validate_openai_responses_payload,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_reference,
)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

# Human-locked base text pricing used only for accounting.
BASE_INPUT_USD_PER_MILLION = 0.20
BASE_OUTPUT_USD_PER_MILLION = 1.20

PAID_UPSTREAM_STAGES = {
    "TOPIC_SELECTION",
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
    "STORY_ARCHITECTURE",
    "ICONIC_CINEMATIC_REVIEW",
    "FINAL_SCRIPT",
    "PRONUNCIATION_AND_PERFORMANCE_GATE",
}

PAID_LUNA_DOWNSTREAM_STAGES = {
    "AUDIO_BOUND_STORYBOARD",
    "LUNA_SEMANTIC_PROMPT_DIRECTION",
    "NARRATION_VISUAL_ALIGNMENT_GATE",
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
}

PAID_LUNA_STAGES = (
    PAID_UPSTREAM_STAGES | PAID_LUNA_DOWNSTREAM_STAGES
)
class LunaTransportV63Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise LunaTransportV63Error("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(path, value, preserve_previous=True)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )


def resolve_luna_model() -> str:
    configured = os.environ.get("SIRAJ_LUNA_MODEL", "").strip()
    if configured:
        return configured
    try:
        from src.application.openai_luna_orchestrator_v1 import LUNA_MODEL
    except Exception as exc:
        raise LunaTransportV63Error(
            "LUNA_MODEL_UNRESOLVED:"
            "SET_SIRAJ_LUNA_MODEL_OR_RESTORE_EXISTING_LUNA_MODEL"
        ) from exc
    value = str(LUNA_MODEL or "").strip()
    if not value:
        raise LunaTransportV63Error("LUNA_MODEL_EMPTY")
    return value


def resolve_reasoning_effort() -> str:
    # Provider API effort names are transport-level. The SIRAJ creative law
    # remains MAX/PRO in the system prompt and review loop.
    configured = os.environ.get(
        "SIRAJ_LUNA_PROVIDER_REASONING_EFFORT",
        "",
    ).strip()
    return configured or "high"


def build_openai_responses_request_payload(
    *,
    model: str,
    system_prompt: str,
    input_payload: Mapping[str, Any],
    use_web_search: bool,
) -> dict[str, Any]:
    """Build the final provider request once, before retry resolution."""

    request_payload: dict[str, Any] = {
        "model": model,
        "store": False,
        "reasoning": {"effort": resolve_reasoning_effort()},
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            input_payload,
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                ],
            },
        ],
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "siraj_v6_3_stage_output",
                "strict": False,
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        },
    }
    if use_web_search:
        request_payload["tools"] = [{"type": "web_search"}]
    validate_openai_responses_payload(request_payload)
    return request_payload


def authorization_path(
    repo_root: Path,
    episode_id: str,
    stage: str,
) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "luna-v6-3"
        / stage.lower()
        / "paid-authorization.json"
    )


def resolve_active_authorization_path(
    repo_root: Path,
    episode_id: str,
    stage: str,
) -> Path:
    canonical = authorization_path(repo_root, episode_id, stage)
    if canonical.is_file() and is_currently_valid(
        repo_root,
        episode_id,
        canonical,
    ):
        return canonical
    versions = canonical.parent / "paid-authorizations-v1"
    candidates = sorted(
        (path for path in versions.glob("*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for candidate in candidates:
        if is_currently_valid(repo_root, episode_id, candidate):
            return candidate
    return canonical


def authorize_stage(
    repo_root: Path,
    episode_id: str,
    stage: str,
    input_payload: Mapping[str, Any],
    confirmation_phrase: str,
) -> Path:
    if stage not in PAID_LUNA_STAGES:
        raise LunaTransportV63Error("UNKNOWN_PAID_UPSTREAM_STAGE:" + stage)

    expected = "أوافق على تنفيذ مرحلة لونا المدفوعة"
    if confirmation_phrase.strip() != expected:
        raise LunaTransportV63Error(
            "EXPLICIT_LUNA_AUTHORIZATION_PHRASE_MISMATCH"
        )

    repo = Path(repo_root).resolve()
    path = resolve_active_authorization_path(repo, episode_id, stage)
    input_sha = canonical_sha256(input_payload)

    if path.is_file() and is_currently_valid(repo, episode_id, path):
        existing = _read(path)
        if (
            existing.get("status") == "ACTIVE"
            and existing.get("stage") == stage
            and existing.get("input_sha256") == input_sha
            and existing.get("automatic_retry") is False
        ):
            return path
        raise LunaTransportV63Error(
            "EXISTING_LUNA_STAGE_AUTHORIZATION_CONFLICT:" + stage
        )

    payload = {
            "schema_version": "siraj-luna-paid-authorization-v6.3",
            "status": "ACTIVE",
            "episode_id": episode_id,
            "stage": stage,
            "model": resolve_luna_model(),
            "input_sha256": input_sha,
            "authorization_source": "EXPLICIT_HUMAN_DESKTOP_CONFIRMATION",
            "confirmation_phrase": expected,
            "assistant_authored_cost_cap_usd": None,
            "assistant_authored_call_cap": None,
            "assistant_authored_output_token_cap": None,
            "automatic_retry": False,
            "automatic_resubmission": False,
            "authorized_at_utc": _now(),
        }
    if path.is_file():
        path = (
            authorization_path(repo, episode_id, stage).parent
            / "paid-authorizations-v1"
            / (input_sha + "-" + str(uuid.uuid4()) + ".json")
        )
        write_new_json(path, payload)
    else:
        _atomic_write(path, payload)
    return path


def _extract_output_text(response: Mapping[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    output = response.get("output")
    texts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    if not texts:
        raise LunaTransportV63Error("OPENAI_OUTPUT_TEXT_MISSING")
    return "\n".join(texts)


def _usage(response: Mapping[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "base_text_cost_usd": 0.0,
        }

    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    details = usage.get("input_tokens_details")
    cached = (
        int(details.get("cached_tokens", 0) or 0)
        if isinstance(details, Mapping)
        else 0
    )
    # The exact long-context doubling threshold is intentionally not guessed.
    base_cost = (
        input_tokens * BASE_INPUT_USD_PER_MILLION
        + output_tokens * BASE_OUTPUT_USD_PER_MILLION
    ) / 1_000_000
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached,
        "base_text_cost_usd": round(base_cost, 10),
        "long_context_multiplier_applied": False,
        "long_context_threshold_known": False,
    }


def _web_calls(response: Mapping[str, Any]) -> int:
    output = response.get("output")
    if not isinstance(output, list):
        return 0
    return sum(
        1
        for item in output
        if isinstance(item, Mapping)
        and item.get("type") == "web_search_call"
    )


def _legacy_execute_authorized_stage_disabled(
    repo_root: Path,
    episode_id: str,
    stage: str,
    *,
    system_prompt: str,
    input_payload: Mapping[str, Any],
    output_path_relative: str,
    use_web_search: bool = False,
) -> Path:
    if stage not in PAID_LUNA_STAGES:
        raise LunaTransportV63Error("UNKNOWN_PAID_UPSTREAM_STAGE:" + stage)

    repo = Path(repo_root).resolve()
    auth_path = authorization_path(repo, episode_id, stage)
    if not auth_path.is_file():
        raise LunaTransportV63Error(
            "EXPLICIT_PAID_AUTHORIZATION_REQUIRED:" + stage
        )
    auth = _read(auth_path)
    input_sha = canonical_sha256(input_payload)
    if (
        auth.get("status") != "ACTIVE"
        or auth.get("stage") != stage
        or auth.get("input_sha256") != input_sha
        or auth.get("automatic_retry") is not False
    ):
        raise LunaTransportV63Error("LUNA_STAGE_AUTHORIZATION_INVALID:" + stage)

    api_key = str(read_openai_api_key() or "").strip()
    if not api_key:
        raise LunaTransportV63Error("OPENAI_API_KEY_REQUIRED")

    attempt_id = str(uuid.uuid4())
    root = (
        repo
        / "projects"
        / episode_id
        / "orchestration"
        / "luna-v6-3"
        / stage.lower()
        / "attempts"
    )
    lock_path = root / f"{attempt_id}.lock.json"
    raw_response_path = root / f"{attempt_id}.raw-response.json"
    ledger_path = (
        repo
        / "projects"
        / episode_id
        / "orchestration"
        / "luna-v6-3"
        / "attempt-ledger.jsonl"
    )

    lock = {
        "schema_version": "siraj-luna-attempt-lock-v6.3",
        "episode_id": episode_id,
        "stage": stage,
        "attempt_id": attempt_id,
        "model": auth.get("model"),
        "input_sha256": input_sha,
        "status": "LOCKED_BEFORE_NETWORK",
        "automatic_retry": False,
        "automatic_resubmission": False,
        "created_at_utc": _now(),
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise LunaTransportV63Error("ATTEMPT_LOCK_COLLISION") from exc
    try:
        os.write(
            descriptor,
            (
                json.dumps(lock, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8"),
        )
    finally:
        os.close(descriptor)

    request_payload: dict[str, Any] = {
        "model": str(auth.get("model")),
        "store": False,
        "reasoning": {
            "effort": resolve_reasoning_effort(),
        },
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            input_payload,
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                ],
            },
        ],
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "siraj_v6_3_stage_output",
                "strict": False,
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        },
    }
    if use_web_search:
        request_payload["tools"] = [{"type": "web_search"}]

    lock["status"] = "NETWORK_REQUEST_STARTED"
    lock["request_sha256"] = canonical_sha256(request_payload)
    _atomic_write(lock_path, lock)
    emit_event(
        repo,
        episode_id,
        "LUNA_REQUEST_STARTED",
        stage=stage,
        message_ar="أُرسل طلب Luna إلى المزود",
        operation="انتظار استجابة Luna",
        input_path=str(auth_path.relative_to(repo)).replace("\\", "/"),
        output_path=output_path_relative,
        provider="OPENAI",
        model=str(auth.get("model") or "Luna"),
        task_uuid=attempt_id,
        status="NETWORK_REQUEST_STARTED",
    )

    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(
            request_payload,
            ensure_ascii=False,
        ).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            raw_bytes = response.read()
        emit_event(
            repo,
            episode_id,
            "LUNA_RESPONSE_RECEIVED",
            stage=stage,
            message_ar="وصل رد Luna من المزود",
            operation="حفظ الرد والتحقق منه",
            provider="OPENAI",
            model=str(auth.get("model") or "Luna"),
            task_uuid=attempt_id,
            status="RESPONSE_RECEIVED",
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        lock["status"] = "PROVIDER_FAILED_NO_AUTOMATIC_RETRY"
        lock["http_status"] = exc.code
        lock["error"] = body[:4000]
        lock["updated_at_utc"] = _now()
        _atomic_write(lock_path, lock)
        _append_jsonl(
            ledger_path,
            {
                "episode_id": episode_id,
                "stage": stage,
                "attempt_id": attempt_id,
                "status": lock["status"],
                "http_status": exc.code,
                "automatic_retry": False,
                "timestamp_utc": _now(),
            },
        )
        raise LunaTransportV63Error(
            "PAID_LUNA_ATTEMPT_FAILED_RETRY_AUTH_REQUIRED:"
            + stage
            + ":HTTP_"
            + str(exc.code)
        ) from exc
    except Exception as exc:
        lock["status"] = (
            "NETWORK_RESULT_UNKNOWN_NO_AUTOMATIC_RESUBMISSION"
        )
        lock["error"] = str(exc)
        lock["updated_at_utc"] = _now()
        _atomic_write(lock_path, lock)
        _append_jsonl(
            ledger_path,
            {
                "episode_id": episode_id,
                "stage": stage,
                "attempt_id": attempt_id,
                "status": lock["status"],
                "automatic_retry": False,
                "timestamp_utc": _now(),
            },
        )
        raise LunaTransportV63Error(
            "PAID_LUNA_NETWORK_RESULT_UNKNOWN_RETRY_AUTH_REQUIRED:"
            + stage
        ) from exc

    try:
        response_payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raw_response_path.write_bytes(raw_bytes)
        lock["status"] = "RAW_RESPONSE_INVALID_JSON_NO_AUTOMATIC_RETRY"
        lock["updated_at_utc"] = _now()
        _atomic_write(lock_path, lock)
        raise LunaTransportV63Error(
            "OPENAI_INVALID_JSON_RESPONSE_RETRY_AUTH_REQUIRED:" + stage
        ) from exc

    # Preserve the full provider response before parsing semantic output.
    _atomic_write(raw_response_path, response_payload)
    emit_event(
        repo,
        episode_id,
        "FILE_WRITTEN",
        stage=stage,
        message_ar="حُفظ رد Luna الخام",
        operation="تحليل الاستجابة الدلالية",
        output_path=str(raw_response_path.relative_to(repo)).replace("\\", "/"),
        provider="OPENAI",
        model=str(auth.get("model") or "Luna"),
        task_uuid=attempt_id,
        status="VALIDATING",
    )

    text = _extract_output_text(response_payload)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        lock["status"] = "LUNA_OUTPUT_INVALID_JSON_NO_AUTOMATIC_RETRY"
        lock["updated_at_utc"] = _now()
        _atomic_write(lock_path, lock)
        raise LunaTransportV63Error(
            "LUNA_OUTPUT_INVALID_JSON_RETRY_AUTH_REQUIRED:" + stage
        ) from exc
    if not isinstance(result, dict):
        raise LunaTransportV63Error("LUNA_OUTPUT_OBJECT_REQUIRED:" + stage)

    output_path = repo / "projects" / episode_id / output_path_relative
    _atomic_write(output_path, result)
    emit_event(
        repo,
        episode_id,
        "FILE_WRITTEN",
        stage=stage,
        message_ar="كُتب الملف الناتج من Luna",
        operation="تسجيل الاستهلاك وإغلاق المحاولة",
        output_path=str(output_path.relative_to(repo)).replace("\\", "/"),
        provider="OPENAI",
        model=str(auth.get("model") or "Luna"),
        task_uuid=attempt_id,
        status="WRITTEN",
    )

    usage = _usage(response_payload)
    web_calls = _web_calls(response_payload)
    ledger_row = {
        "episode_id": episode_id,
        "stage": stage,
        "attempt_id": attempt_id,
        "response_id": response_payload.get("id"),
        "status": "COMPLETE",
        "model": auth.get("model"),
        **usage,
        "web_search_calls": web_calls,
        "automatic_retry": False,
        "timestamp_utc": _now(),
    }
    _append_jsonl(ledger_path, ledger_row)

    lock.update(
        {
            "status": "COMPLETE",
            "response_id": response_payload.get("id"),
            "raw_response_path_relative": str(
                raw_response_path.relative_to(repo)
            ).replace("\\", "/"),
            "output_path_relative": str(
                output_path.relative_to(repo)
            ).replace("\\", "/"),
            "usage": usage,
            "web_search_calls": web_calls,
            "completed_at_utc": _now(),
        }
    )
    _atomic_write(lock_path, lock)
    emit_event(
        repo,
        episode_id,
        "LUNA_TASK_COMPLETED",
        stage=stage,
        message_ar="اكتملت محاولة Luna",
        operation="اكتملت مهمة Luna",
        output_path=str(output_path.relative_to(repo)).replace("\\", "/"),
        last_completed_file=str(output_path.relative_to(repo)).replace("\\", "/"),
        provider="OPENAI",
        model=str(auth.get("model") or "Luna"),
        task_uuid=attempt_id,
        actual_cost_usd=float(usage.get("base_text_cost_usd") or 0.0),
        status="COMPLETE",
    )
    return output_path


# Stable Phase 0 transport override.  Kept at the public symbol so all existing
# stage adapters inherit the single paid-operation boundary without a patch
# layer or caller migration.

# SIRAJ_EXPLICIT_PAID_RETRY_V9
def _resolve_explicit_paid_retry_v9(
    repo: Path,
    episode_id: str,
    stage: str,
    request_payload: Mapping[str, Any],
    *,
    canonical_request_identity_sha256: str,
    provider_payload_sha256_value: str,
) -> dict[str, Any] | None:
    retry_root = (
        Path(repo).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "explicit-paid-retry-v9"
    )
    plan_path = retry_root / "semantic-editorial-and-technical-qa-plan.json"
    if stage != "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA" or not plan_path.is_file():
        return None

    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise LunaTransportV63Error(
            "EXPLICIT_PAID_RETRY_PLAN_INVALID:" + str(exc)
        ) from exc

    expected_identity = str(canonical_request_identity_sha256 or "").strip()
    expected_provider_payload = str(provider_payload_sha256_value or "").strip()
    if len(expected_identity) != 64 or len(expected_provider_payload) != 64:
        raise LunaTransportV63Error(
            "EXPLICIT_PAID_RETRY_CANONICAL_IDENTITY_INVALID"
        )
    if (
        plan.get("schema_version")
        != "siraj-explicit-paid-retry-plan-v10"
        or plan.get("episode_id") != episode_id
        or plan.get("stage") != stage
        or plan.get("canonical_request_identity_sha256")
        != expected_identity
        or plan.get("provider_payload_sha256")
        != expected_provider_payload
        or not str(plan.get("prior_attempt_id") or "").strip()
        or not str(plan.get("new_attempt_id") or "").strip()
    ):
        raise LunaTransportV63Error("EXPLICIT_PAID_RETRY_PLAN_BINDING_INVALID")

    auth_rel = str(plan.get("authorization_path") or "").strip()
    if not auth_rel:
        raise LunaTransportV63Error(
            "SEPARATE_HUMAN_RETRY_AUTHORIZATION_REQUIRED:"
            + str(plan.get("prior_attempt_id"))
        )
    auth_path = Path(auth_rel)
    if not auth_path.is_absolute():
        auth_path = Path(repo).resolve() / auth_path

    if not auth_path.is_file():
        raise LunaTransportV63Error(
            "SEPARATE_HUMAN_RETRY_AUTHORIZATION_REQUIRED:"
            + str(plan.get("prior_attempt_id"))
        )

    try:
        retry_auth = json.loads(auth_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise LunaTransportV63Error(
            "EXPLICIT_PAID_RETRY_AUTHORIZATION_INVALID:" + str(exc)
        ) from exc

    required = {
        "status": "ACTIVE",
        "episode_id": episode_id,
        "stage": stage,
        "prior_attempt_id": plan.get("prior_attempt_id"),
        "new_attempt_id": plan.get("new_attempt_id"),
        "canonical_request_identity_sha256": expected_identity,
        "provider_payload_sha256": expected_provider_payload,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "one_shot": True,
    }
    for key, expected in required.items():
        if retry_auth.get(key) != expected:
            raise LunaTransportV63Error(
                "EXPLICIT_PAID_RETRY_AUTHORIZATION_BINDING_INVALID:" + key
            )
    if not str(retry_auth.get("reason") or "").strip():
        raise LunaTransportV63Error(
            "EXPLICIT_PAID_RETRY_AUTHORIZATION_REASON_REQUIRED"
        )

    planned_attempt_id = str(plan["new_attempt_id"])
    events_path = (
        Path(repo).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "paid-operation-attempts-v1"
        / planned_attempt_id
        / "attempt-events.jsonl"
    )
    if events_path.is_file():
        rows = []
        for line in events_path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                raise LunaTransportV63Error(
                    "EXPLICIT_PAID_RETRY_ATTEMPT_EVENTS_INVALID"
                )
        statuses = [str(row.get("status") or "") for row in rows]
        if any(status in {"RESULT_PERSISTED", "COMPLETE"} for status in statuses):
            pass
        elif rows:
            raise LunaTransportV63Error(
                "EXPLICIT_PAID_RETRY_AUTHORIZATION_CONSUMED_NEW_HUMAN_AUTH_REQUIRED:"
                + planned_attempt_id
            )

    return {
        "prior_attempt_id": str(plan["prior_attempt_id"]),
        "new_attempt_id": planned_attempt_id,
        "authorization": retry_auth,
        "canonical_request_identity_sha256": expected_identity,
        "provider_payload_sha256": expected_provider_payload,
    }

def execute_authorized_stage(
    repo_root: Path,
    episode_id: str,
    stage: str,
    *,
    system_prompt: str,
    input_payload: Mapping[str, Any],
    output_path_relative: str,
    use_web_search: bool = False,
) -> Path:
    # SIRAJ_EP002_QA_PAID_GATEWAY_ROUTE_FIX_V6_4_1
    # Canonical paid_operation_gateway path below is now reachable.
    if stage not in PAID_LUNA_STAGES:
        raise LunaTransportV63Error("UNKNOWN_PAID_UPSTREAM_STAGE:" + stage)
    repo = Path(repo_root).resolve()
    auth_path = resolve_active_authorization_path(repo, episode_id, stage)
    if not auth_path.is_file():
        raise LunaTransportV63Error("EXPLICIT_PAID_AUTHORIZATION_REQUIRED:" + stage)
    auth = _read(auth_path)
    input_sha = canonical_sha256(input_payload)
    if (auth.get("status") != "ACTIVE" or auth.get("stage") != stage
            or auth.get("input_sha256") != input_sha
            or auth.get("automatic_retry") is not False):
        raise LunaTransportV63Error("LUNA_STAGE_AUTHORIZATION_INVALID:" + stage)
    api_key = str(read_openai_api_key() or "").strip()
    if not api_key:
        raise LunaTransportV63Error("OPENAI_API_KEY_REQUIRED")
    request_payload = build_openai_responses_request_payload(
        model=str(auth.get("model")),
        system_prompt=system_prompt,
        input_payload=input_payload,
        use_web_search=use_web_search,
    )
    canonical_request_identity_sha256 = build_paid_operation_identity(
        episode_id=episode_id,
        stage=stage,
        operation_type="OPENAI_RESPONSES",
        provider="OPENAI",
        model=str(auth.get("model")),
        provider_contract_version=PROVIDER_CONTRACT_VERSION,
        payload=request_payload,
        input_artifact_hashes={"stage_input": input_sha},
        operation_nonce=input_sha,
        authorization_mode="EPISODE_MASTER",
    )
    final_provider_payload_sha256 = provider_payload_sha256(request_payload)
    retry_context = _resolve_explicit_paid_retry_v9(
        repo,
        episode_id,
        stage,
        request_payload,
        canonical_request_identity_sha256=canonical_request_identity_sha256,
        provider_payload_sha256_value=final_provider_payload_sha256,
    )
    attempt_id = (
        str(retry_context["new_attempt_id"])
        if retry_context
        else str(uuid.uuid4())
    )
    auth_episode = "NEXT_NEW_EPISODE" if episode_id == "episode-bootstrap-next" else episode_id
    paid_request = PaidOperationRequest(
        repo_root=repo, episode_id=episode_id, stage=stage,
        operation_type="OPENAI_RESPONSES", provider="OPENAI",
        model=str(auth.get("model")), provider_contract_version=PROVIDER_CONTRACT_VERSION,
        payload=request_payload, input_artifact_hashes={"stage_input": input_sha},
        master_authorization_reference=master_authorization_reference(repo, auth_episode),
        operation_nonce=input_sha, attempt_id=attempt_id,
        retry_authorization_reference=(
            retry_context.get("authorization") if retry_context else None
        ),
        prior_attempt_id=(
            retry_context.get("prior_attempt_id") if retry_context else None
        ),
    )
    emit_event(repo, episode_id, "LUNA_REQUEST_STARTED", stage=stage,
               provider="OPENAI", model=str(auth.get("model")),
               task_uuid=attempt_id, status="TRANSPORT_STARTING")
    paid_result, response_payload = execute_paid_json(
        paid_request,
        http_json_transport(
            url=OPENAI_RESPONSES_URL, method="POST", payload=request_payload,
            headers={"Authorization": "Bearer " + api_key,
                     "Content-Type": "application/json"}, timeout_seconds=600,
        ),
        telemetry=lambda event_type, payload: bool(
            emit_event(repo, episode_id, event_type, stage=stage,
                       provider="OPENAI", model=str(auth.get("model")),
                       task_uuid=attempt_id,
                       status=str(payload.get("status") or "COMPLETE")).get(
                           "telemetry_persisted", False)
        ),
    )
    emit_event(repo, episode_id, "LUNA_RESPONSE_RECEIVED", stage=stage,
               provider="OPENAI", model=str(auth.get("model")),
               task_uuid=attempt_id, status="RESULT_PERSISTED")
    text = _extract_output_text(response_payload)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LunaTransportV63Error(
            "LUNA_OUTPUT_INVALID_JSON_RETRY_AUTH_REQUIRED:" + stage
        ) from exc
    if not isinstance(result, dict):
        raise LunaTransportV63Error("LUNA_OUTPUT_OBJECT_REQUIRED:" + stage)
    output_path = repo / "projects" / episode_id / output_path_relative
    _atomic_write(output_path, result)
    usage = _usage(response_payload)
    ledger_path = repo / "projects" / episode_id / "orchestration" / "luna-v6-3" / "attempt-ledger.jsonl"
    _append_jsonl(ledger_path, {
        "episode_id": episode_id, "stage": stage, "attempt_id": attempt_id,
        "gateway_attempt_id": paid_result.attempt_id,
        "response_id": response_payload.get("id"), "status": "COMPLETE",
        "model": auth.get("model"), **usage,
        "web_search_calls": _web_calls(response_payload), "automatic_retry": False,
        "timestamp_utc": _now(),
    })
    emit_event(repo, episode_id, "TASK_COMPLETED", stage=stage,
               output_path=str(output_path.relative_to(repo)).replace("\\", "/"),
               provider="OPENAI", model=str(auth.get("model")),
               task_uuid=attempt_id, actual_cost_usd=float(usage["base_text_cost_usd"]),
               status="COMPLETE")
    return output_path
