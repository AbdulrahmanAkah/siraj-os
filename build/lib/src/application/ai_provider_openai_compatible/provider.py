"""OpenAI-compatible provider implementation, isolated from domain layers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.application.ai_integration import AIProviderError
from src.application.operations_common import deterministic_id, integrity_hash
from src.application.security import PolicyDecision


@dataclass(frozen=True)
class CredentialReference:
    reference: str


class CredentialResolver(Protocol):
    def resolve(self, reference: CredentialReference) -> str | None: ...


@dataclass(frozen=True)
class OpenAICompatibleProviderConfig:
    provider_id: str = "OPENAI_COMPATIBLE"
    model_id: str = "gpt-4.1-mini"
    endpoint: str = "https://api.openai.com/v1/responses"
    timeout_seconds: float = 20.0
    maximum_context_characters: int = 20_000
    maximum_output_characters: int = 8_000
    allowed_models: tuple[str, ...] = ("gpt-4.1-mini",)
    raw_response_retention: str = "HASH_ONLY"


@dataclass(frozen=True)
class ExternalAIExecutionPolicy:
    allow_external: bool = False
    allowed_providers: tuple[str, ...] = ("OPENAI_COMPATIBLE",)
    allowed_models: tuple[str, ...] = ("gpt-4.1-mini",)
    data_classification: str = "INTERNAL"
    approved: bool = False

    def decide(self, action: str, provider_id: str, model_id: str) -> PolicyDecision:
        if action == "STORE_RAW_PROVIDER_RESPONSE":
            return PolicyDecision("DENY", "RAW_RESPONSE_DISABLED")
        if action == "ACCESS_SECRET" and not self.allow_external:
            return PolicyDecision("DENY", "EXTERNAL_AI_DISABLED")
        if action in {"SEND_TO_EXTERNAL_PROVIDER", "USE_NETWORK"}:
            if self.data_classification == "RESTRICTED":
                return PolicyDecision("DENY", "RESTRICTED_EXTERNAL_TRANSMISSION_DENIED")
            if self.data_classification == "SENSITIVE" and not self.approved:
                return PolicyDecision("REQUIRES_APPROVAL", "SENSITIVE_EXTERNAL_APPROVAL_REQUIRED")
            if not self.allow_external or provider_id not in self.allowed_providers or model_id not in self.allowed_models:
                return PolicyDecision("DENY", "EXTERNAL_PROVIDER_OR_MODEL_DENIED")
        return PolicyDecision("ALLOW", "EXTERNAL_AI_EXPLICIT_ALLOW")


class RecordedProviderTransport:
    """Stable fixture transport used by offline tests; it performs no I/O."""

    def __init__(self, responses: dict[str, dict[str, Any]]):
        self.responses = responses

    def __call__(self, _request: dict[str, Any], _credential: str, _config: OpenAICompatibleProviderConfig) -> dict[str, Any]:
        key = _request.get("fixture", "success")
        return dict(self.responses[key])


class OpenAICompatibleProvider:
    """One opt-in real provider adapter with normalized, sanitized failures."""

    capabilities = ("TEXT_GENERATION", "STRUCTURED_OUTPUT", "CITATION_AWARE_OUTPUT", "MULTILINGUAL")

    def __init__(self, config: OpenAICompatibleProviderConfig, credential_reference: CredentialReference, credential_resolver: CredentialResolver, policy: ExternalAIExecutionPolicy, transport: Callable[[dict[str, Any], str, OpenAICompatibleProviderConfig], dict[str, Any]] | None = None):
        self.config = config
        self.credential_reference = credential_reference
        self.credential_resolver = credential_resolver
        self.policy = policy
        self.transport = transport

    def describe_capabilities(self) -> list[str]:
        return list(self.capabilities)

    def _deny_unless_allowed(self) -> None:
        for action in ("SEND_TO_EXTERNAL_PROVIDER", "USE_NETWORK", "ACCESS_SECRET"):
            decision = self.policy.decide(action, self.config.provider_id, self.config.model_id)
            if decision.decision != "ALLOW":
                raise AIProviderError(f"POLICY_DENIED:{decision.rule_id}")

    def _normalise_error(self, error: BaseException) -> AIProviderError:
        if isinstance(error, AIProviderError):
            return error
        if isinstance(error, HTTPError):
            mapping = {401: "AUTHENTICATION_FAILURE", 403: "PERMISSION_DENIED", 429: "RATE_LIMIT", 408: "TIMEOUT"}
            return AIProviderError(mapping.get(error.code, "PROVIDER_SERVICE_FAILURE"))
        if isinstance(error, (TimeoutError, socket.timeout)):
            return AIProviderError("TIMEOUT")
        if isinstance(error, URLError):
            return AIProviderError("CONNECTION_FAILURE")
        return AIProviderError("PROVIDER_SERVICE_FAILURE")

    def _live_transport(self, request: dict[str, Any], credential: str, config: OpenAICompatibleProviderConfig) -> dict[str, Any]:
        body = json.dumps({"model": config.model_id, "input": request["text"], "max_output_tokens": request.get("max_output_tokens", 512)}, ensure_ascii=False).encode("utf-8")
        http_request = Request(config.endpoint, data=body, headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"}, method="POST")
        with urlopen(http_request, timeout=config.timeout_seconds) as response:  # nosec B310: policy-gated explicit endpoint
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        if payload.get("refusal"):
            raise AIProviderError("CONTENT_POLICY_REFUSAL")
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        if isinstance(payload.get("text"), str):
            return payload["text"]
        output = payload.get("output", [])
        if output and isinstance(output[0], dict):
            content = output[0].get("content", [])
            if content and isinstance(content[0], dict) and isinstance(content[0].get("text"), str):
                return content[0]["text"]
        raise AIProviderError("MALFORMED_RESPONSE")

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.config.model_id not in self.config.allowed_models:
            raise AIProviderError("UNSUPPORTED_CAPABILITY")
        text = str(request.get("text", ""))
        if not text:
            raise AIProviderError("EMPTY_RESPONSE")
        if len(text) > self.config.maximum_context_characters:
            raise AIProviderError("CONTEXT_LIMIT_EXCEEDED")
        self._deny_unless_allowed()
        credential = self.credential_resolver.resolve(self.credential_reference)
        if not credential:
            raise AIProviderError("AUTHENTICATION_FAILURE")
        try:
            payload = (self.transport or self._live_transport)(request, credential, self.config)
            text = self._extract_text(payload)
        except BaseException as error:
            raise self._normalise_error(error) from None
        if len(text) > self.config.maximum_output_characters:
            raise AIProviderError("CONTEXT_LIMIT_EXCEEDED")
        if request.get("structured") and not isinstance(payload.get("structured", payload.get("output_parsed")), dict):
            raise AIProviderError("INVALID_STRUCTURED_OUTPUT")
        return {
            "request_id": str(payload.get("id") or deterministic_id("provider_request", [self.config.provider_id, self.config.model_id, integrity_hash(request)])),
            "response_id": str(payload.get("id") or deterministic_id("provider_response", [integrity_hash(payload)])),
            "text": text,
            "citations": list(payload.get("citations", request.get("evidence_ids", []))),
            "claims": list(payload.get("claims", [])),
            "usage": dict(payload.get("usage", {})),
            "raw_output_hash": integrity_hash(payload),
            "provider": self.config.provider_id,
            "model": self.config.model_id,
        }
