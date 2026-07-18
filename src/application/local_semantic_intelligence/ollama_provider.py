"""UTF-8-safe Ollama chat adapter restricted to local loopback execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import http.client
import json
import socket
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

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
from .semantic_prompts import (
    PROMPT_CONTRACTS,
    chat_messages,
    schema_for_stage,
)


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_SAFE_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "date",
    "x-request-id",
    "request-id",
}


def serialize_json_utf8(payload: dict[str, Any]) -> bytes:
    """Canonical request bytes: UTF-8, no BOM, no platform default encoding."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _has_arabic(value: Any) -> bool:
    if isinstance(value, str):
        return any("\u0600" <= character <= "\u06ff" for character in value)
    if isinstance(value, dict):
        return any(_has_arabic(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_arabic(item) for item in value)
    return False


def _has_corrupt_question_marks(value: Any) -> bool:
    if isinstance(value, str):
        return "???" in value
    if isinstance(value, dict):
        return any(_has_corrupt_question_marks(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_corrupt_question_marks(item) for item in value)
    return False


def _safe_headers(headers: Any) -> dict[str, str]:
    return {
        key.lower(): str(value)
        for key, value in headers.items()
        if key.lower() in _SAFE_RESPONSE_HEADERS
    }


@dataclass(frozen=True)
class OllamaLocalSemanticConfig:
    endpoint: str = "http://127.0.0.1:11434"
    model_reference: str = "qwen3:4b-instruct"
    model_digest: str = "UNRESOLVED"
    model_policy: str = "PILOT_MODEL_ONLY"
    profile: str = "LOCAL_ONLY"
    connect_timeout_seconds: float = 10.0
    model_load_timeout_seconds: float = 300.0
    generation_timeout_seconds: float = 900.0
    overall_stage_timeout_seconds: float = 900.0
    retries: int = 1
    stream: bool = False
    temperature: float = 0.0
    raw_response_retention: str = "SAFE_LOCAL_ARTIFACT"
    hardware: SemanticHardwareProfile = SemanticHardwareProfile()

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("OLLAMA_ENDPOINT_MUST_BE_HTTP")
        if self.profile == "LOCAL_ONLY" and parsed.hostname not in _LOOPBACK_HOSTS:
            raise ValueError("OLLAMA_LOCAL_ONLY_REQUIRES_LOOPBACK")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("OLLAMA_ENDPOINT_MUST_BE_ORIGIN_ONLY")
        if self.retries < 0 or self.retries > 1:
            raise ValueError("OLLAMA_RETRIES_OUT_OF_RANGE")
        if self.hardware.concurrency != 1:
            raise ValueError("LOCAL_LOW_MEMORY_REQUIRES_CONCURRENCY_ONE")
        if self.stream or self.temperature != 0:
            raise ValueError("OLLAMA_PILOT_REQUIRES_DETERMINISTIC_NON_STREAMING")
        if min(
            self.connect_timeout_seconds,
            self.model_load_timeout_seconds,
            self.generation_timeout_seconds,
            self.overall_stage_timeout_seconds,
        ) <= 0:
            raise ValueError("OLLAMA_TIMEOUT_MUST_BE_POSITIVE")


Transport = Callable[[str, str, dict[str, Any] | None, dict[str, float]], dict[str, Any]]


class OllamaLocalSemanticProvider(SemanticExtractionProvider):
    """A single-model `/api/chat` provider; it never uses cloud fallback."""

    def __init__(
        self,
        config: OllamaLocalSemanticConfig,
        *,
        transport: Transport | None = None,
    ):
        self.config = config
        self.identity = ProviderIdentity(
            provider_id="OLLAMA_LOCAL_SEMANTIC",
            model_id=config.model_reference or "UNCONFIGURED",
            model_digest=config.model_digest,
            prompt_version=PROMPT_VERSION,
        )
        self._transport = transport or self._http_transport
        self._active_request = False

    def _url(self, path: str) -> str:
        return self.config.endpoint.rstrip("/") + path

    def _timeouts(self) -> dict[str, float]:
        return {
            "connect": self.config.connect_timeout_seconds,
            "model_load": self.config.model_load_timeout_seconds,
            "generation": self.config.generation_timeout_seconds,
            "overall_stage": self.config.overall_stage_timeout_seconds,
        }

    @staticmethod
    def _http_transport(
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        timeouts: dict[str, float],
    ) -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.hostname not in _LOOPBACK_HOSTS:
            raise SemanticProviderError("OLLAMA_LOCAL_ONLY_REQUIRES_LOOPBACK")
        connection = http.client.HTTPConnection(
            parsed.hostname,
            parsed.port or 80,
            timeout=timeouts["connect"],
        )
        body = serialize_json_utf8(payload) if payload is not None else None
        try:
            connection.connect()
            if connection.sock is not None:
                connection.sock.settimeout(timeouts["generation"])
            connection.request(
                method,
                parsed.path or "/",
                body=body,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            raw = response.read()
            if response.status >= 400:
                raise SemanticProviderError(
                    "OLLAMA_HTTP_" + str(response.status),
                    retryable=response.status >= 500,
                )
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise SemanticProviderError("OLLAMA_RESPONSE_NOT_OBJECT")
            decoded["_safe_response_headers"] = _safe_headers(response.headers)
            return decoded
        finally:
            connection.close()

    @staticmethod
    def _normalise_error(error: BaseException, stage: str) -> SemanticProviderError:
        if isinstance(error, SemanticProviderError):
            return error
        if isinstance(error, HTTPError):
            mapping = {
                404: "OLLAMA_MODEL_OR_ENDPOINT_NOT_FOUND",
                408: "OLLAMA_GENERATION_TIMEOUT",
                429: "OLLAMA_RATE_LIMIT",
                504: "OLLAMA_GENERATION_TIMEOUT",
                507: "OLLAMA_INSUFFICIENT_MEMORY",
            }
            return SemanticProviderError(
                mapping.get(error.code, "OLLAMA_HTTP_FAILURE"),
                retryable=error.code >= 500,
            )
        if isinstance(error, (TimeoutError, socket.timeout)):
            return SemanticProviderError(
                "OLLAMA_CONNECT_TIMEOUT" if stage == "CONNECT" else "OLLAMA_GENERATION_TIMEOUT",
                retryable=True,
            )
        if isinstance(error, (URLError, ConnectionError, OSError)):
            return SemanticProviderError("OLLAMA_UNAVAILABLE", retryable=True)
        message = str(error).lower()
        if any(token in message for token in ("out of memory", "insufficient memory", "oom")):
            return SemanticProviderError("OLLAMA_INSUFFICIENT_MEMORY")
        return SemanticProviderError("OLLAMA_PROVIDER_FAILURE")

    def _call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        stage: str = "CONNECT",
    ) -> dict[str, Any]:
        if self._active_request:
            raise SemanticProviderError("OLLAMA_PARALLEL_REQUEST_DENIED")
        last: SemanticProviderError | None = None
        for attempt in range(self.config.retries + 1):
            started = time.perf_counter_ns()
            self._active_request = True
            try:
                result = self._transport(
                    method,
                    self._url(path),
                    payload,
                    self._timeouts(),
                )
                result.setdefault("_request_duration_ns", time.perf_counter_ns() - started)
                result.setdefault("_retry_count", attempt)
                return result
            except BaseException as error:
                last = self._normalise_error(error, stage)
                if not last.retryable or attempt >= self.config.retries:
                    raise last from None
            finally:
                self._active_request = False
        raise last or SemanticProviderError("OLLAMA_PROVIDER_FAILURE")

    def _refresh_identity(self, payload: dict[str, Any]) -> None:
        digest = str(payload.get("digest") or payload.get("model_digest") or self.identity.model_digest)
        if digest and digest != self.identity.model_digest:
            self.identity = ProviderIdentity(
                provider_id=self.identity.provider_id,
                model_id=self.identity.model_id,
                model_digest=digest,
                prompt_version=self.identity.prompt_version,
            )

    def health_check(self) -> SemanticProviderHealth:
        try:
            payload = self._call("GET", "/api/tags")
        except SemanticProviderError as error:
            return SemanticProviderHealth("UNAVAILABLE", self.identity, error.code)
        models = [item for item in payload.get("models", []) if isinstance(item, dict)]
        match = next(
            (item for item in models if str(item.get("name", "")) == self.config.model_reference),
            None,
        )
        if not self.config.model_reference:
            return SemanticProviderHealth("UNAVAILABLE", self.identity, "MODEL_REFERENCE_NOT_CONFIGURED")
        if match is None:
            return SemanticProviderHealth("UNAVAILABLE", self.identity, "MODEL_NOT_INSTALLED")
        self._refresh_identity(match)
        return SemanticProviderHealth("AVAILABLE", self.identity, "OLLAMA_AND_MODEL_AVAILABLE")

    def inspect_model(self) -> dict[str, Any]:
        if not self.config.model_reference:
            raise SemanticProviderError("MODEL_REFERENCE_NOT_CONFIGURED")
        payload = self._call(
            "POST",
            "/api/show",
            {"name": self.config.model_reference},
            stage="MODEL_LOAD",
        )
        self._refresh_identity(payload)
        details = payload.get("details", {})
        return {
            "status": "AVAILABLE",
            "identity": asdict(self.identity),
            "family": str(details.get("family", "UNSPECIFIED")),
            "parameter_size": str(details.get("parameter_size", "UNSPECIFIED")),
            "quantization_level": str(details.get("quantization_level", "UNSPECIFIED")),
            "capabilities": sorted(str(item) for item in payload.get("capabilities", [])),
            "context_target": self.config.hardware.context_tokens,
            "model_policy": self.config.model_policy,
            "safe_response_headers": payload.get("_safe_response_headers", {}),
            "raw_payload_retained": False,
        }

    @staticmethod
    def _safe_raw_response(payload: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"authorization", "api_key", "credential", "token", "prompt"}
        return {
            str(key): value
            for key, value in payload.items()
            if str(key).lower() not in forbidden and not str(key).startswith("_")
        }

    def _chat(self, stage: str, request: dict[str, Any]) -> dict[str, Any]:
        if not self.config.model_reference:
            raise SemanticProviderError("MODEL_REFERENCE_NOT_CONFIGURED")
        source_envelope = {
            "source_data_is_untrusted": True,
            "source_id": request.get("source_id", ""),
            "locator": request.get("locator", ""),
            "original_text": request.get("original_text", ""),
            "prior_stage_outputs": request.get("prior_stage_outputs", {}),
            "execution_plan": request.get("execution_plan", ""),
        }
        messages = chat_messages(stage, source_envelope)
        payload = self._call(
            "POST",
            "/api/chat",
            {
                "model": self.config.model_reference,
                "messages": messages,
                "stream": False,
                "format": schema_for_stage(stage),
                "keep_alive": self.config.hardware.keep_alive,
                "options": {
                    "temperature": 0,
                    "num_ctx": self.config.hardware.context_tokens,
                    "num_predict": self.config.hardware.maximum_output_tokens,
                },
            },
            stage="GENERATION",
        )
        self._refresh_identity(payload)
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise SemanticProviderError("OLLAMA_EMPTY_RESPONSE")
        try:
            structured = json.loads(content)
        except json.JSONDecodeError as error:
            raise SemanticProviderError("OLLAMA_INVALID_STRUCTURED_OUTPUT") from error
        if not isinstance(structured, dict):
            raise SemanticProviderError("OLLAMA_STRUCTURED_OUTPUT_NOT_OBJECT")
        if _has_arabic(source_envelope["original_text"]) and _has_corrupt_question_marks(structured):
            raise SemanticProviderError("OLLAMA_CORRUPT_UTF8_OUTPUT")
        load_duration = int(payload.get("load_duration", 0) or 0)
        if load_duration > int(self.config.model_load_timeout_seconds * 1_000_000_000):
            raise SemanticProviderError("OLLAMA_MODEL_LOAD_TIMEOUT")
        structured.setdefault("schema_version", SEMANTIC_SCHEMA_VERSION)
        structured["provider_metadata"] = {
            "provider_id": self.identity.provider_id,
            "model_id": self.identity.model_id,
            "model_digest": self.identity.model_digest,
            "model_policy": self.config.model_policy,
            "prompt_version": self.identity.prompt_version,
            "prompt_contract": stage,
            "prompt_schema_hash": integrity_hash(schema_for_stage(stage)),
            "response_hash": integrity_hash(content),
            "safe_response_headers": payload.get("_safe_response_headers", {}),
            "retry_count": int(payload.get("_retry_count", 0)),
            "tokens": {
                "input": int(payload.get("prompt_eval_count", 0) or 0),
                "output": int(payload.get("eval_count", 0) or 0),
            },
            "provider_timings_ns": {
                "total": int(payload.get("total_duration", 0) or 0),
                "load": load_duration,
                "prompt_evaluation": int(payload.get("prompt_eval_duration", 0) or 0),
                "evaluation": int(payload.get("eval_duration", 0) or 0),
                "request": int(payload.get("_request_duration_ns", 0) or 0),
            },
            "tokens_per_second": round(
                int(payload.get("eval_count", 0) or 0)
                / max(int(payload.get("eval_duration", 0) or 1) / 1_000_000_000, 0.000001),
                4,
            ),
            "raw_response_retained": self.config.raw_response_retention == "SAFE_LOCAL_ARTIFACT",
        }
        if self.config.raw_response_retention == "SAFE_LOCAL_ARTIFACT":
            structured["safe_raw_provider_response"] = self._safe_raw_response(payload)
        return structured

    def classify_structure(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._chat("STRUCTURAL_ANALYSIS", request)

    def extract_combined(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._chat("SIMPLE_HISTORICAL_COMBINED", request)

    def extract_mentions(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._chat("MENTION_EXTRACTION", request)

    def extract_events_relations(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._chat("EVENT_RELATION_EXTRACTION", request)

    def extract_claims_attribution(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._chat("CLAIM_ATTRIBUTION", request)

    def extract_isnad(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._chat("ISNAD_EXTRACTION", request)

    def extract_poetry_sira(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._chat("POETRY_SIRA_EXTRACTION", request)

    def verify_evidence(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"status": "DETERMINISTIC_ONLY", "issues": []}

    def critique_extraction(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._chat("CRITICAL_REVIEW", request)

    def unload(self) -> dict[str, Any]:
        if not self.config.model_reference:
            return {"status": "NOT_LOADED", "reason_code": "MODEL_REFERENCE_NOT_CONFIGURED"}
        self._call(
            "POST",
            "/api/chat",
            {
                "model": self.config.model_reference,
                "messages": [],
                "stream": False,
                "keep_alive": 0,
            },
            stage="UNLOAD",
        )
        return {
            "status": "UNLOADED",
            "provider_id": self.identity.provider_id,
            "model_id": self.identity.model_id,
        }


__all__ = [
    "OllamaLocalSemanticConfig",
    "OllamaLocalSemanticProvider",
    "PROMPT_CONTRACTS",
    "serialize_json_utf8",
]
