"""Google Gemini adapter for bounded cloud semantic critical-regression runs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Protocol

from src.application.operations_common import integrity_hash

from .models import (
    PROMPT_VERSION,
    ProviderIdentity,
    SEMANTIC_SCHEMA_VERSION,
    SemanticHardwareProfile,
    SemanticProviderError,
    SemanticProviderHealth,
)
from .provider import SemanticExtractionProvider
from .semantic_prompts import chat_messages
from .gemini_schema import (
    GEMINI_SCHEMA_VERSION,
    GeminiResponseSchemaMismatch,
    GeminiSchemaError,
    gemini_schema_for_route,
    parse_route_response,
    schema_check,
)
from .critical_regression import (
    CRITICAL_SCHEMA_VERSION,
    critical_root,
    prepare_critical_4,
    run_critical_4,
)
from .orchestrator import atomic_write_json, atomic_write_text


GEMINI_PROVIDER_ID = "GEMINI_SEMANTIC"
GEMINI_PROMPT_VERSION = "gemini-critical-prompts-v2"
GEMINI_ALLOWED_HOSTS = ("generativelanguage.googleapis.com",)
_ROUTE_STAGES = {
    "PERSON_AND_STATUS": "CRITICAL_PERSON_AND_STATUS",
    "APPOINTMENT_AND_OFFICE": "CRITICAL_APPOINTMENT_AND_OFFICE",
    "ISNAD": "CRITICAL_ISNAD",
    "SIRA_POETRY": "CRITICAL_SIRA_POETRY",
}
_RETRYABLE = {
    "GEMINI_TIMEOUT",
    "GEMINI_RATE_LIMITED",
    "GEMINI_NETWORK_FAILURE",
    "GEMINI_PROVIDER_FAILURE",
}

_MODEL_FALLBACK_ERRORS = {
    "GEMINI_QUOTA_EXCEEDED",
    "GEMINI_RATE_LIMITED",
    "GEMINI_TIMEOUT",
    "GEMINI_NETWORK_FAILURE",
    "GEMINI_PROVIDER_FAILURE",
    "GEMINI_MODEL_NOT_AVAILABLE",
    "GEMINI_FINISH_REASON_FAILURE",
    "GEMINI_EMPTY_RESPONSE",
    "GEMINI_JSON_PARSE_FAILED",
    "GEMINI_RESPONSE_SCHEMA_MISMATCH",
}


def redact_sensitive(value: Any, secret: str = "") -> Any:
    """Remove API-key-like values from diagnostics and persisted artifacts."""

    if isinstance(value, str):
        result = value.replace(secret, "[REDACTED]") if secret else value
        if "AIza" in result or "api_key" in result.lower() or "authorization" in result.lower():
            return "[REDACTED]"
        return result
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if any(token in str(key).lower() for token in ("key", "token", "authorization", "secret"))
            else redact_sensitive(item, secret)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item, secret) for item in value]
    return value


class GeminiTransport(Protocol):
    api_host: str

    def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: dict[str, Any],
    ) -> Any: ...


class GoogleGenAITransport:
    """Lazy official google-genai transport; no legacy SDK import is used."""

    api_host = "generativelanguage.googleapis.com"

    def __init__(self, api_key: str):
        try:
            from google import genai  # type: ignore[import-not-found]
            from google.genai import types  # type: ignore[import-not-found]
        except ImportError as error:
            raise SemanticProviderError("GEMINI_SDK_NOT_INSTALLED") from error
        self._types = types
        self._client = genai.Client(api_key=api_key)

    def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: dict[str, Any],
    ) -> Any:
        config_arguments: dict[str, Any] = {
            "temperature": config["temperature"],
            "max_output_tokens": config["max_output_tokens"],
            "response_mime_type": config["response_mime_type"],
            "response_schema": config["response_schema"],
        }

        # Gemini 3 accepts thinking_level. Do not send that model-specific
        # option to Gemini 2.5 fallback models.
        if model.startswith("gemini-3"):
            config_arguments["thinking_config"] = (
                self._types.ThinkingConfig(
                    thinking_level=config["thinking_level"],
                )
            )

        typed_config = self._types.GenerateContentConfig(
            **config_arguments
        )

        return self._client.models.generate_content(
            model=model,
            contents=contents,
            config=typed_config,
        )


@dataclass(frozen=True)
class GeminiSemanticConfig:
    provider_id: str = GEMINI_PROVIDER_ID
    model_reference: str = "gemini-3.5-flash"
    fallback_models: tuple[str, ...] = (
        "gemini-3.1-flash-lite",
        "gemini-3-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    )
    timeout_seconds: float = 90.0
    retries: int = 1
    temperature: float = 0.0
    maximum_output_tokens: int = 128
    thinking_level: str = "low"
    structured_output_enabled: bool = True
    external_network_allowed: bool = False
    batch_mode: bool = False
    data_policy_acknowledged: bool = False
    maximum_requests_per_run: int = 8
    maximum_input_tokens_per_run: int = 12_000
    maximum_output_tokens_per_run: int = 1_024
    abort_on_budget_exceeded: bool = True
    hardware: SemanticHardwareProfile = field(
        default_factory=lambda: SemanticHardwareProfile(
            concurrency=1,
            maximum_output_tokens=128,
            stage_timeout_seconds=90.0,
        )
    )

    def __post_init__(self) -> None:
        if self.provider_id != GEMINI_PROVIDER_ID:
            raise SemanticProviderError("GEMINI_PROVIDER_ID_INVALID")
        if not self.model_reference.strip():
            raise SemanticProviderError("GEMINI_MODEL_NOT_AVAILABLE")

        model_chain = (
            self.model_reference,
            *self.fallback_models,
        )

        if any(not str(model).strip() for model in model_chain):
            raise SemanticProviderError(
                "GEMINI_MODEL_NOT_AVAILABLE"
            )

        if len(set(model_chain)) != len(model_chain):
            raise SemanticProviderError(
                "GEMINI_MODEL_CHAIN_DUPLICATE"
            )

        if self.batch_mode:
            raise SemanticProviderError("GEMINI_BATCH_MODE_NOT_SUPPORTED")
        if self.hardware.concurrency != 1:
            raise SemanticProviderError("GEMINI_CONCURRENCY_MUST_BE_ONE")
        if self.maximum_output_tokens < 128:
            raise SemanticProviderError("GEMINI_OUTPUT_TOKEN_LIMIT_TOO_LOW")
        if self.thinking_level.lower() not in {"low", "medium", "high"}:
            raise SemanticProviderError("GEMINI_THINKING_LEVEL_INVALID")


def load_gemini_config(path: str | os.PathLike[str]) -> GeminiSemanticConfig:
    payload = json.loads(open(path, encoding="utf-8-sig").read())
    provider = payload.get("provider", {})
    limits = payload.get("budget_limits", {})
    hardware = payload.get("hardware", {})

    raw_fallback_models = provider.get(
        "fallback_models",
        [
            "gemini-3.1-flash-lite",
            "gemini-3-flash",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ],
    )

    if not isinstance(raw_fallback_models, list):
        raise SemanticProviderError(
            "GEMINI_FALLBACK_MODELS_INVALID"
        )

    fallback_models = tuple(
        str(model).strip()
        for model in raw_fallback_models
        if str(model).strip()
    )

    return GeminiSemanticConfig(
        provider_id=str(provider.get("provider_id", GEMINI_PROVIDER_ID)),
        model_reference=str(
            provider.get(
                "model_reference",
                "gemini-3.5-flash",
            )
        ),
        fallback_models=fallback_models,
        timeout_seconds=float(provider.get("timeout_seconds", 90)),
        retries=int(provider.get("retries", 1)),
        temperature=float(provider.get("temperature", 0)),
        maximum_output_tokens=int(provider.get("maximum_output_tokens", 128)),
        thinking_level=str(provider.get("thinking_level", "low")),
        structured_output_enabled=bool(provider.get("structured_output_enabled", True)),
        external_network_allowed=bool(provider.get("external_network_allowed", False)),
        batch_mode=bool(provider.get("batch_mode", False)),
        data_policy_acknowledged=bool(provider.get("data_policy_acknowledged", False)),
        maximum_requests_per_run=int(limits.get("maximum_requests_per_run", 8)),
        maximum_input_tokens_per_run=int(limits.get("maximum_input_tokens_per_run", 12_000)),
        maximum_output_tokens_per_run=int(limits.get("maximum_output_tokens_per_run", 1_024)),
        abort_on_budget_exceeded=bool(limits.get("abort_on_budget_exceeded", True)),
        hardware=SemanticHardwareProfile(
            concurrency=int(hardware.get("concurrency", 1)),
            context_tokens=int(hardware.get("context_tokens", 1536)),
            maximum_output_tokens=int(provider.get("maximum_output_tokens", 128)),
            stage_timeout_seconds=float(provider.get("timeout_seconds", 90)),
            keep_alive="0",
            checkpoint_after_each_stage=True,
        ),
    )


def _field(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _normalise_error(error: BaseException) -> SemanticProviderError:
    if isinstance(error, SemanticProviderError):
        return error
    status_value = _field(error, "status_code", "code", default=0) or 0
    try:
        status = int(status_value)
    except (TypeError, ValueError):
        status = 0
    name = type(error).__name__.lower()
    raw_message = str(error)
    message = raw_message.lower()
    details = {
        "exception_class": type(error).__name__,
        "http_status": status or None,
        "google_error_code": str(_field(error, "code", default="") or "") or None,
        "google_error_message": redact_sensitive(raw_message),
    }
    if status == 400 and any(token in message for token in (
        "schema", "response_schema", "response schema", "json schema", "invalid argument",
    )):
        return SemanticProviderError("GEMINI_REQUEST_SCHEMA_REJECTED", details=details)
    if status in {401, 403} or "authentication" in message or "api key" in message:
        return SemanticProviderError("GEMINI_AUTH_FAILED", details=details)
    if status == 404 or "not found" in message or "model" in message and "available" in message:
        return SemanticProviderError("GEMINI_MODEL_NOT_AVAILABLE", details=details)
    if status == 429 or "quota" in message:
        return SemanticProviderError("GEMINI_QUOTA_EXCEEDED", retryable=False, details=details)
    if "rate" in message and "limit" in message:
        return SemanticProviderError("GEMINI_RATE_LIMITED", retryable=True, details=details)
    if "timeout" in name or "timeout" in message:
        return SemanticProviderError("GEMINI_TIMEOUT", retryable=True, details=details)
    if any(token in name for token in ("connection", "network")):
        return SemanticProviderError("GEMINI_NETWORK_FAILURE", retryable=True, details=details)
    if 500 <= status <= 599:
        return SemanticProviderError("GEMINI_PROVIDER_FAILURE", retryable=True, details=details)
    if "safety" in message or "blocked" in message:
        return SemanticProviderError("GEMINI_SAFETY_BLOCK", details=details)
    return SemanticProviderError("GEMINI_PROVIDER_FAILURE", retryable=True, details=details)


def _finish_reason(response: Any) -> str:
    direct = _field(response, "finish_reason", default=None)
    if direct is not None:
        return str(direct)
    candidates = _field(response, "candidates", default=[]) or []
    if candidates:
        return str(_field(candidates[0], "finish_reason", default="UNKNOWN"))
    return "UNKNOWN"


def _response_text(response: Any) -> str:
    """Read text without assuming the convenience ``response.text`` exists."""

    direct = _field(response, "text", default=None)
    if isinstance(direct, str) and direct.strip():
        return direct
    candidates = _field(response, "candidates", default=[]) or []
    for candidate in candidates:
        content = _field(candidate, "content", default={}) or {}
        for part in _field(content, "parts", default=[]) or []:
            text = _field(part, "text", default=None)
            if isinstance(text, str) and text.strip():
                return text
    return ""


def _finish_is_success(reason: str) -> bool:
    normalized = reason.upper()
    return normalized == "STOP" or normalized.endswith(".STOP")


def _record_failure(request: dict[str, Any], error: SemanticProviderError, stage: str) -> None:
    callback = request.get("record_failure")
    if not callable(callback):
        return
    payload = redact_sensitive({
        "provider_id": GEMINI_PROVIDER_ID,
        "route": request.get("route", ""),
        "model": request.get("model_reference", ""),
        "schema_version": GEMINI_SCHEMA_VERSION,
        "failure_stage": stage,
        "error_code": error.code,
        **error.details,
    })
    try:
        callback(payload)
    except BaseException:
        # Diagnostics must never replace the normalized provider error.
        return


class GeminiSemanticProvider(SemanticExtractionProvider):
    """Independent Gemini adapter used only through the provider boundary."""

    def __init__(
        self,
        config: GeminiSemanticConfig,
        *,
        api_key_getter: Callable[[], str | None] | None = None,
        transport: GeminiTransport | None = None,
    ):
        self.config = config
        self._api_key_getter = api_key_getter or (lambda: os.environ.get("GEMINI_API_KEY"))
        self._transport = transport
        self.identity = ProviderIdentity(
            provider_id=config.provider_id,
            model_id=config.model_reference,
            model_digest="UNRESOLVED",
            prompt_version=GEMINI_PROMPT_VERSION,
        )
        self.request_count = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def _api_key(self) -> str:
        key = self._api_key_getter()
        if not key or not str(key).strip():
            raise SemanticProviderError("GEMINI_API_KEY_MISSING")
        return str(key).strip()

    def _resolved_transport(self) -> GeminiTransport:
        if not self.config.external_network_allowed:
            raise SemanticProviderError("GEMINI_EXTERNAL_NETWORK_NOT_ALLOWED")
        if not self.config.data_policy_acknowledged:
            raise SemanticProviderError("GEMINI_DATA_POLICY_NOT_ACKNOWLEDGED")
        transport = self._transport or GoogleGenAITransport(self._api_key())
        if str(getattr(transport, "api_host", "")) not in GEMINI_ALLOWED_HOSTS:
            raise SemanticProviderError("GEMINI_ENDPOINT_NOT_ALLOWED")
        return transport

    def health_check(self) -> SemanticProviderHealth:
        try:
            self._api_key()
        except SemanticProviderError as error:
            return SemanticProviderHealth("UNAVAILABLE", self.identity, error.code, localhost_only=False)
        if not self.config.external_network_allowed:
            return SemanticProviderHealth("UNAVAILABLE", self.identity, "GEMINI_EXTERNAL_NETWORK_NOT_ALLOWED", localhost_only=False)
        return SemanticProviderHealth("CONFIGURED", self.identity, "GEMINI_MANUAL_NETWORK_RUN_REQUIRED", localhost_only=False)

    def inspect_model(self) -> dict[str, Any]:
        return {
            "status": "CONFIGURED", "identity": self.identity,
            "structured_output": self.config.structured_output_enabled,
            "primary_model": self.config.model_reference,
            "fallback_models": list(
                self.config.fallback_models
            ),
            "model_chain": [
                self.config.model_reference,
                *self.config.fallback_models,
            ],
            "external_network_allowed": self.config.external_network_allowed,
            "data_policy_acknowledged": self.config.data_policy_acknowledged,
            "batch_mode": False, "allowed_hosts": list(GEMINI_ALLOWED_HOSTS),
            "free_tier_privacy_warning": "DATA_NOT_ASSUMED_PRIVATE",
        }

    def _generate(
        self,
        stage: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        if stage not in _ROUTE_STAGES.values():
            raise SemanticProviderError(
                "GEMINI_ROUTE_SCHEMA_NOT_FOUND"
            )

        if not self.config.structured_output_enabled:
            raise SemanticProviderError(
                "GEMINI_STRUCTURED_OUTPUT_REQUIRED"
            )

        route = str(request.get("route", ""))

        if _ROUTE_STAGES.get(route) != stage:
            raise SemanticProviderError(
                "GEMINI_ROUTE_SCHEMA_NOT_FOUND"
            )

        messages = chat_messages(stage, {
            "source_data_is_untrusted": True,
            "source_id": request.get("source_id", ""),
            "locator": request.get("locator", ""),
            "original_text": request.get("original_text", ""),
            "route": request.get("route", ""),
            "repair": bool(request.get("repair", False)),
            "repair_reason": request.get("repair_reason", ""),
            "rejected_item": request.get(
                "rejected_item",
                {},
            ),
            "accepted_output": request.get(
                "accepted_output",
                {},
            ),
        })

        contents = "\n\n".join(
            f"{item['role']}: {item['content']}"
            for item in messages
        )

        try:
            schema = gemini_schema_for_route(route)
        except GeminiSchemaError as error:
            provider_error = SemanticProviderError(
                "GEMINI_LOCAL_SCHEMA_CONSTRUCTION_FAILED",
                details={
                    "exception_class": type(error).__name__,
                    "message": redact_sensitive(str(error)),
                },
            )
            _record_failure(
                request,
                provider_error,
                "REQUEST_SCHEMA_REJECTED",
            )
            raise provider_error from error

        generation_config = {
            "temperature": self.config.temperature,
            "max_output_tokens": (
                self.config.maximum_output_tokens
            ),
            "response_mime_type": "application/json",
            "response_schema": schema,
            "thinking_level": (
                self.config.thinking_level.lower()
            ),
        }

        model_chain = (
            self.config.model_reference,
            *self.config.fallback_models,
        )

        model_failures: list[dict[str, Any]] = []
        transport = self._resolved_transport()

        for model_index, model_reference in enumerate(model_chain):
            attempt = 0

            while attempt <= self.config.retries:
                if (
                    self.request_count
                    >= self.config.maximum_requests_per_run
                ):
                    raise SemanticProviderError(
                        "GEMINI_BUDGET_REQUEST_LIMIT",
                        details={
                            "maximum_requests_per_run": (
                                self.config
                                .maximum_requests_per_run
                            ),
                            "request_count": self.request_count,
                            "model_failures": model_failures,
                        },
                    )

                active_request = {
                    **request,
                    "model_reference": model_reference,
                }

                try:
                    self.request_count += 1
                    started = time.perf_counter_ns()

                    response = transport.generate_content(
                        model=model_reference,
                        contents=contents,
                        config=generation_config,
                    )

                    elapsed = (
                        time.perf_counter_ns() - started
                    )
                    finish_reason = _finish_reason(response)
                    response_text = _response_text(response)

                    if not _finish_is_success(finish_reason):
                        raise SemanticProviderError(
                            "GEMINI_FINISH_REASON_FAILURE",
                            details={
                                "finish_reason": finish_reason,
                            },
                        )

                    if not response_text:
                        raise SemanticProviderError(
                            "GEMINI_EMPTY_RESPONSE",
                            details={
                                "finish_reason": finish_reason,
                            },
                        )

                    try:
                        output = json.loads(response_text)
                    except json.JSONDecodeError as error:
                        raise SemanticProviderError(
                            "GEMINI_JSON_PARSE_FAILED",
                            details={
                                "finish_reason": finish_reason,
                                "exception_class": (
                                    type(error).__name__
                                ),
                            },
                        ) from error

                    if not isinstance(output, dict):
                        raise SemanticProviderError(
                            "GEMINI_JSON_PARSE_FAILED",
                            details={
                                "finish_reason": finish_reason,
                                "json_root_type": (
                                    type(output).__name__
                                ),
                            },
                        )

                    try:
                        output = parse_route_response(
                            route,
                            output,
                        )
                    except GeminiResponseSchemaMismatch as error:
                        raise SemanticProviderError(
                            "GEMINI_RESPONSE_SCHEMA_MISMATCH",
                            details={
                                "finish_reason": finish_reason,
                                "exception_class": (
                                    type(error).__name__
                                ),
                            },
                        ) from error

                    usage = _field(
                        response,
                        "usage_metadata",
                        "usage",
                        default={},
                    ) or {}

                    input_tokens = int(
                        _field(
                            usage,
                            "prompt_token_count",
                            "input_tokens",
                            default=0,
                        )
                        or 0
                    )
                    output_tokens = int(
                        _field(
                            usage,
                            "candidates_token_count",
                            "output_tokens",
                            default=0,
                        )
                        or 0
                    )
                    cached_tokens = int(
                        _field(
                            usage,
                            "cached_content_token_count",
                            "cached_tokens",
                            default=0,
                        )
                        or 0
                    )

                    self.input_tokens += input_tokens
                    self.output_tokens += output_tokens

                    if self.config.abort_on_budget_exceeded and (
                        self.input_tokens
                        > self.config.maximum_input_tokens_per_run
                        or self.output_tokens
                        > self.config.maximum_output_tokens_per_run
                    ):
                        raise SemanticProviderError(
                            "GEMINI_BUDGET_TOKEN_LIMIT"
                        )

                    output["provider_metadata"] = {
                        "provider_id": GEMINI_PROVIDER_ID,
                        "model": model_reference,
                        "primary_model": (
                            self.config.model_reference
                        ),
                        "fallback_used": model_index > 0,
                        "fallback_depth": model_index,
                        "model_chain": list(model_chain),
                        "model_failures": redact_sensitive(
                            model_failures
                        ),
                        "request_count": self.request_count,
                        "retry_count": attempt,
                        "finish_reason": finish_reason,
                        "provider_request_id": str(
                            _field(
                                response,
                                "response_id",
                                "request_id",
                                default="UNAVAILABLE",
                            )
                        ),
                        "schema_version": (
                            GEMINI_SCHEMA_VERSION
                        ),
                        "prompt_version": (
                            self.identity.prompt_version
                        ),
                        "usage": {
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "cached_tokens": cached_tokens,
                            "total_tokens": (
                                input_tokens + output_tokens
                            ),
                        },
                        "latency_ns": elapsed,
                        "cost_status": "UNKNOWN",
                        "raw_response_hash": integrity_hash(
                            redact_sensitive({
                                "text": response_text,
                            })
                        ),
                    }

                    output["raw_provider_response"] = (
                        redact_sensitive(
                            {
                                "text": response_text,
                                "finish_reason": finish_reason,
                            },
                            self._api_key(),
                        )
                    )

                    return output

                except BaseException as raw_error:
                    error = _normalise_error(raw_error)

                    failure = {
                        "model": model_reference,
                        "model_index": model_index,
                        "attempt": attempt,
                        "error_code": error.code,
                        "retryable": error.retryable,
                        "details": redact_sensitive(
                            error.details
                        ),
                    }

                    is_retryable = (
                        error.retryable
                        and error.code in _RETRYABLE
                        and attempt < self.config.retries
                    )

                    if is_retryable:
                        checkpoint = request.get(
                            "checkpoint_before_retry"
                        )

                        if callable(checkpoint):
                            checkpoint({
                                "status": "RETRY_PENDING",
                                "model": model_reference,
                                "error": error.code,
                                "attempt": attempt + 1,
                            })

                        attempt += 1
                        continue

                    model_failures.append(failure)

                    has_next_model = (
                        model_index + 1 < len(model_chain)
                    )
                    may_fallback = (
                        error.code in _MODEL_FALLBACK_ERRORS
                    )

                    if may_fallback and has_next_model:
                        checkpoint = request.get(
                            "checkpoint_before_retry"
                        )

                        if callable(checkpoint):
                            checkpoint({
                                "status": (
                                    "MODEL_FALLBACK_PENDING"
                                ),
                                "failed_model": model_reference,
                                "next_model": model_chain[
                                    model_index + 1
                                ],
                                "error": error.code,
                                "model_failures": (
                                    redact_sensitive(
                                        model_failures
                                    )
                                ),
                            })

                        break

                    if may_fallback and not has_next_model:
                        failure_stage = {
                            "GEMINI_EMPTY_RESPONSE": (
                                "EMPTY_RESPONSE"
                            ),
                            "GEMINI_FINISH_REASON_FAILURE": (
                                "FINISH_REASON_FAILURE"
                            ),
                            "GEMINI_JSON_PARSE_FAILED": (
                                "JSON_PARSE_FAILED"
                            ),
                            "GEMINI_RESPONSE_SCHEMA_MISMATCH": (
                                "RESPONSE_SCHEMA_MISMATCH"
                            ),
                        }.get(
                            error.code,
                            "PROVIDER_REQUEST_FAILED",
                        )

                        if len(model_chain) == 1:
                            _record_failure(
                                active_request,
                                error,
                                failure_stage,
                            )

                            raise error from raw_error

                        final_error = SemanticProviderError(
                            "GEMINI_ALL_MODELS_FAILED",
                            details={
                                "route": route,
                                "model_chain": list(model_chain),
                                "model_failures": (
                                    redact_sensitive(
                                        model_failures
                                    )
                                ),
                                "last_error_code": error.code,
                            },
                        )

                        _record_failure(
                            active_request,
                            final_error,
                            failure_stage,
                        )

                        raise final_error from raw_error

                    # Fatal shared configuration, authentication,
                    # policy, local-schema, or budget errors must not
                    # be hidden by switching models.
                    failure_stage = {
                        "GEMINI_REQUEST_SCHEMA_REJECTED": (
                            "REQUEST_SCHEMA_REJECTED"
                        ),
                        "GEMINI_EMPTY_RESPONSE": (
                            "EMPTY_RESPONSE"
                        ),
                        "GEMINI_FINISH_REASON_FAILURE": (
                            "FINISH_REASON_FAILURE"
                        ),
                        "GEMINI_JSON_PARSE_FAILED": (
                            "JSON_PARSE_FAILED"
                        ),
                        "GEMINI_RESPONSE_SCHEMA_MISMATCH": (
                            "RESPONSE_SCHEMA_MISMATCH"
                        ),
                    }.get(
                        error.code,
                        "PROVIDER_REQUEST_FAILED",
                    )

                    _record_failure(
                        active_request,
                        error,
                        failure_stage,
                    )

                    raise error

        raise SemanticProviderError(
            "GEMINI_ALL_MODELS_FAILED",
            details={
                "route": route,
                "model_chain": list(model_chain),
                "model_failures": redact_sensitive(
                    model_failures
                ),
            },
        )


    def extract_critical_route(self, route: str, request: dict[str, Any]) -> dict[str, Any]:
        stage = _ROUTE_STAGES.get(route)
        if stage is None:
            raise SemanticProviderError("GEMINI_ROUTE_SCHEMA_NOT_FOUND")
        return self._generate(stage, request)

    def classify_structure(self, request: dict[str, Any]) -> dict[str, Any]: raise SemanticProviderError("GEMINI_CRITICAL_4_ONLY")
    def extract_mentions(self, request: dict[str, Any]) -> dict[str, Any]: raise SemanticProviderError("GEMINI_CRITICAL_4_ONLY")
    def extract_events_relations(self, request: dict[str, Any]) -> dict[str, Any]: raise SemanticProviderError("GEMINI_CRITICAL_4_ONLY")
    def extract_claims_attribution(self, request: dict[str, Any]) -> dict[str, Any]: raise SemanticProviderError("GEMINI_CRITICAL_4_ONLY")
    def verify_evidence(self, request: dict[str, Any]) -> dict[str, Any]: return {"status": "DETERMINISTIC_ONLY", "issues": []}
    def critique_extraction(self, request: dict[str, Any]) -> dict[str, Any]: raise SemanticProviderError("GEMINI_CRITICAL_4_ONLY")
    def unload(self) -> dict[str, Any]: return {"status": "NOT_APPLICABLE", "provider_id": GEMINI_PROVIDER_ID}


def prepare_gemini_critical_4(semantic_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Prepare auditable Gemini comparison artifacts without a network call."""

    critical = prepare_critical_4(semantic_root)
    root = critical_root(semantic_root)
    pending = {
        "schema_version": CRITICAL_SCHEMA_VERSION,
        "provider_id": GEMINI_PROVIDER_ID,
        "status": "PENDING_MANUAL_GEMINI_RUN",
        "quality_claim": "NONE_UNTIL_MANUAL_RUN_AND_HUMAN_REVIEW",
        "cases": [
            {
                "case_id": item["case_id"], "route": item["route"],
                "human_notes": item["human_notes"],
                "old_qwen_output": item["old_model_reference"],
                "gemini_raw_output": "PENDING_MANUAL_GEMINI_RUN",
                "gemini_validated_output": "PENDING_MANUAL_GEMINI_RUN",
                "baseline": "CANDIDATE_GENERATOR_ONLY",
            }
            for item in critical["cases"]
        ],
    }
    atomic_write_json(root / "gemini-critical-4-comparison.json", pending)
    atomic_write_text(
        root / "gemini-critical-4-comparison.md",
        "# Gemini Critical-4 comparison\n\nStatus: `PENDING_MANUAL_GEMINI_RUN`\n\nNo provider-quality conclusion has been made.\n",
    )
    return pending


def run_gemini_schema_check(output_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Validate all route schemas locally; this function never resolves a transport."""

    report = schema_check()
    report["artifact"] = "gemini-schema-check-report.json"
    atomic_write_json(Path(output_root) / report["artifact"], report)
    return report


def probe_gemini_route(provider: GeminiSemanticProvider, route: str) -> dict[str, Any]:
    """One explicit safe Arabic request for a real schema acceptance probe."""

    if route != "PERSON_AND_STATUS":
        raise SemanticProviderError("GEMINI_PROBE_ROUTE_NOT_ALLOWED")
    text = "قال أحمد بن حنبل إن فلاناً مدلس."
    output = provider.extract_critical_route(route, {
        "source_id": "gemini-probe-public-text",
        "locator": "siraj://gemini-probe/person-and-status",
        "original_text": text,
        "route": route,
        "probe": True,
    })
    metadata = output.get("provider_metadata", {})
    return {
        "status": "PASS",
        "route": route,
        "finish_reason": metadata.get("finish_reason", "UNKNOWN"),
        "response_parse_status": "PASS",
        "provider_metadata": metadata,
    }


def run_gemini_critical_4(
    semantic_root: str | os.PathLike[str],
    provider: GeminiSemanticProvider,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Execute only Critical-4 and publish provider-specific audit artifacts."""

    root = critical_root(semantic_root)
    prepare_gemini_critical_4(semantic_root)

    def record_failure(payload: dict[str, Any]) -> None:
        atomic_write_json(root / "gemini-critical-4-last-failure.json", {
            "schema_version": CRITICAL_SCHEMA_VERSION,
            "provider_id": GEMINI_PROVIDER_ID,
            "model": provider.config.model_reference,
            "diagnostic": redact_sensitive(payload),
        })

    try:
        run = run_critical_4(
            semantic_root,
            provider,
            force=force,
            failure_callback=record_failure,
        )
    except SemanticProviderError as error:
        failure_stage = {
            "GEMINI_REQUEST_SCHEMA_REJECTED": "REQUEST_SCHEMA_REJECTED",
            "GEMINI_EMPTY_RESPONSE": "EMPTY_RESPONSE",
            "GEMINI_FINISH_REASON_FAILURE": "FINISH_REASON_FAILURE",
            "GEMINI_JSON_PARSE_FAILED": "JSON_PARSE_FAILED",
            "GEMINI_RESPONSE_SCHEMA_MISMATCH": "RESPONSE_SCHEMA_MISMATCH",
            "GEMINI_EVIDENCE_VALIDATION_FAILED": "EVIDENCE_VALIDATION_FAILED",
        }.get(error.code, "PROVIDER_REQUEST_FAILED")
        record_failure({
            "route": error.details.get("route", ""),
            "failure_stage": error.details.get("failure_stage", failure_stage),
            "error_code": error.code,
            **error.details,
        })
        raise
    performance_cases = []
    validation_cases = []
    comparison_cases = []
    critical = prepare_critical_4(semantic_root)
    by_case = {item["case_id"]: item for item in critical["cases"]}
    for result in run["cases"]:
        output = result["output"]
        metadata = output.get("provider_metadata", {})
        performance_cases.append({
            "case_id": result["case_id"], "calls": result["calls"],
            "duration_ns": result["duration_ns"], "usage": metadata.get("usage", {}),
            "latency_ns": metadata.get("latency_ns", 0),
            "finish_reason": metadata.get("finish_reason", "UNKNOWN"),
            "retry_count": metadata.get("retry_count", 0),
        })
        validation_cases.append({
            "case_id": result["case_id"], "validation": result["validation"],
        })
        source = by_case[result["case_id"]]
        comparison_cases.append({
            "case_id": result["case_id"], "route": result["route"],
            "human_notes": source["human_notes"],
            "old_qwen_output": source["old_model_reference"],
            "baseline": "CANDIDATE_GENERATOR_ONLY",
            "gemini_raw_output": output.get("raw_provider_response", {}),
            "gemini_validated_output": {"validation": result["validation"], "output": output},
            "error_categories": [],
        })
        if result["status"] == "FAIL":
            record_failure({
                "route": result["route"],
                "failure_stage": "EVIDENCE_VALIDATION_FAILED",
                "error_code": "GEMINI_EVIDENCE_VALIDATION_FAILED",
                "rejections": result["validation"].get("rejections", []),
            })
    manifest = {**run, "provider_id": GEMINI_PROVIDER_ID}
    atomic_write_json(root / "gemini-critical-4-run-manifest.json", manifest)
    atomic_write_json(root / "gemini-critical-4-performance.json", {"provider_id": GEMINI_PROVIDER_ID, "cases": performance_cases, "cost_status": "UNKNOWN"})
    atomic_write_json(root / "gemini-critical-4-validation.json", {"provider_id": GEMINI_PROVIDER_ID, "cases": validation_cases})
    comparison = {"provider_id": GEMINI_PROVIDER_ID, "status": run["status"], "quality_claim": "NONE_AUTOMATIC", "cases": comparison_cases}
    atomic_write_json(root / "gemini-critical-4-comparison.json", comparison)
    atomic_write_text(root / "gemini-critical-4-comparison.md", f"# Gemini Critical-4 comparison\n\nStatus: `{run['status']}`\n\nHuman review is required before any quality conclusion.\n")
    return manifest


__all__ = [
    "GEMINI_ALLOWED_HOSTS", "GEMINI_PROVIDER_ID", "GeminiSemanticConfig",
    "GeminiSemanticProvider", "GeminiTransport", "GoogleGenAITransport",
    "load_gemini_config", "probe_gemini_route", "redact_sensitive", "run_gemini_schema_check",
    "prepare_gemini_critical_4", "run_gemini_critical_4",
]
