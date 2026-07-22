"""Guarded Gemini implementation of the evidence-bound script writer protocol.

It is inert until composition supplies an explicit transport.  No secrets or
prompts are persisted by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Protocol


@dataclass(frozen=True)
class GeminiNarrativeWriterConfig:
    provider_id: str = "gemini"
    model_id: str = "gemini-2.5-flash"
    maximum_input_tokens: int = 24000
    maximum_output_tokens: int = 30000
    temperature: float = 0.2
    structured_output_required: bool = True
    grounding_policy: str = "DISABLED_SOURCE_PACKAGE_ONLY"
    prompt_version: str = "evidence-to-script-gemini-v1"
    schema_version: str = "evidence-bound-script-writer-v1"


class GeminiNarrativeTransport(Protocol):
    def generate_json(self, *, model_id: str, prompt: str, maximum_output_tokens: int, temperature: float) -> dict[str, Any]: ...


class GoogleGenAINarrativeTransport:
    """Lazy official-SDK transport; never constructed by a default pipeline."""
    def __init__(self, api_key: str) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("GEMINI_API_KEY_MISSING")
        self._api_key = api_key

    def generate_json(self, *, model_id: str, prompt: str, maximum_output_tokens: int, temperature: float) -> dict[str, Any]:
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("GEMINI_SDK_MISSING") from error
        response = genai.Client(api_key=self._api_key).models.generate_content(
            model=model_id, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=temperature, max_output_tokens=maximum_output_tokens),
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("GEMINI_EMPTY_RESPONSE")
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise RuntimeError("GEMINI_JSON_PARSE_FAILED") from error
        if not isinstance(value, dict):
            raise RuntimeError("GEMINI_STRUCTURED_RESPONSE_INVALID")
        return value


class GeminiEvidenceBoundScriptWriter:
    """Production-callable writer; the adapter keeps evidence validation authoritative."""
    writer_id = "gemini-evidence-bound-script-writer"
    writer_version = "1"
    requires_external = True

    def __init__(self, config: GeminiNarrativeWriterConfig, transport: GeminiNarrativeTransport) -> None:
        self.config, self.transport = config, transport
        # This becomes part of the adapter's cache fingerprint via writer_version.
        self.writer_version = "1:" + sha256(json.dumps({
            "provider": config.provider_id, "model": config.model_id,
            "prompt": config.prompt_version, "schema": config.schema_version,
            "temperature": config.temperature, "max_output": config.maximum_output_tokens,
        }, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    def generate(self, *, evidence_package: dict[str, Any], brief: dict[str, Any], outline: dict[str, Any]) -> dict[str, Any]:
        claims = [{key: claim.get(key) for key in ("claim_id", "normalized_claim", "source_refs", "evidence_refs", "dispute_status", "restrictions")} for claim in evidence_package.get("claims", [])]
        payload = {
            "task": "Return JSON only for an evidence-bound Arabic documentary script.",
            "rules": ["Use only supplied claims; never add facts.", "Each factual block retains claim_ids, source_refs and evidence_refs.", "Mark disputed claims and include uncertainty_language.", "Use direct quotes only from supplied quotations."],
            "brief": brief, "outline": outline, "claims": claims, "quotations": evidence_package.get("quotations", []),
            "response_contract": {"sections": [{"section_id": "string", "order": "integer", "heading": "string", "narration_blocks": [{"block_id": "string", "block_type": "string", "assertion_class": "string", "text": "string", "claim_ids": ["string"], "source_refs": ["string"], "evidence_refs": ["string"], "citation_required": True, "citation_status": "BOUND", "confidence": "string", "disputed": False, "uncertainty_language": None, "direct_quote": False, "quote_id": None}]}], "quotation_index": {}},
        }
        return self.transport.generate_json(model_id=self.config.model_id, prompt=json.dumps(payload, ensure_ascii=False, separators=(",", ":")), maximum_output_tokens=self.config.maximum_output_tokens, temperature=self.config.temperature)
