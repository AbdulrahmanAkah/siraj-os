"""Provider boundary and deterministic test provider for semantic extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

from src.application.operations_common import deterministic_id, integrity_hash

from .models import (
    PROMPT_VERSION,
    ProviderIdentity,
    SemanticProviderHealth,
)


class SemanticExtractionProvider(ABC):
    """Public provider-neutral contract used by the semantic orchestrator."""

    identity: ProviderIdentity

    @abstractmethod
    def health_check(self) -> SemanticProviderHealth: ...

    @abstractmethod
    def inspect_model(self) -> dict[str, Any]: ...

    @abstractmethod
    def classify_structure(self, request: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def extract_mentions(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def extract_combined(self, request: dict[str, Any]) -> dict[str, Any]:
        """Optional bounded combined extraction for SIMPLE_HISTORICAL plans."""
        raise NotImplementedError("COMBINED_EXTRACTION_NOT_SUPPORTED")

    @abstractmethod
    def extract_events_relations(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]: ...

    @abstractmethod
    def extract_claims_attribution(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]: ...

    def extract_isnad(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.extract_claims_attribution(request)

    def extract_poetry_sira(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.extract_events_relations(request)

    def extract_critical_route(
        self,
        route: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """One bounded extraction call for a targeted regression route."""
        payload = dict(request)
        payload["route"] = route
        return self.extract_combined(payload)

    @abstractmethod
    def verify_evidence(self, request: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def critique_extraction(self, request: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def unload(self) -> dict[str, Any]: ...


class DeterministicSemanticTestProvider(SemanticExtractionProvider):
    """Offline provider with stable, injectable stage responses."""

    def __init__(
        self,
        responses: dict[str, dict[str, Any]] | None = None,
        *,
        fail_stage: str | None = None,
    ):
        self.identity = ProviderIdentity(
            provider_id="DETERMINISTIC_SEMANTIC_TEST",
            model_id="fake-arabic-semantic-v1",
            model_digest=integrity_hash("fake-arabic-semantic-v1"),
            prompt_version=PROMPT_VERSION,
        )
        self.responses = deepcopy(responses or {})
        self.fail_stage = fail_stage
        self.calls: list[str] = []
        self.unloaded = False

    def health_check(self) -> SemanticProviderHealth:
        return SemanticProviderHealth(
            status="AVAILABLE",
            provider=self.identity,
            reason_code="DETERMINISTIC_OFFLINE_PROVIDER",
        )

    def inspect_model(self) -> dict[str, Any]:
        return {
            "status": "AVAILABLE",
            "identity": self.identity,
            "capabilities": [
                "STRUCTURED_JSON",
                "ARABIC_TEXT",
                "DETERMINISTIC_TEST_OUTPUT",
            ],
            "external_network": False,
        }

    def _result(self, stage: str, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(stage)
        if self.fail_stage == stage:
            raise RuntimeError(f"FAKE_PROVIDER_FAILURE:{stage}")
        if stage in self.responses:
            return deepcopy(self.responses[stage])
        safe_request = {
            key: value for key, value in request.items()
            if not callable(value)
        }
        text = str(safe_request.get("original_text", ""))
        structure = {
            "segment_type": "NON_HISTORICAL"
            if not text.strip()
            else "HISTORICAL_NARRATIVE",
            "subtypes": [],
            "heading_ranges": [],
            "prose_ranges": (
                [{"start": 0, "end": len(text), "text": text}]
                if text
                else []
            ),
            "poetry_ranges": [],
            "isnad_ranges": [],
            "matn_ranges": [],
            "footnote_ranges": [],
            "quoted_source_ranges": [],
            "requires_previous_context": False,
            "requires_next_context": False,
            "confidence": 1.0,
            "rationale_codes": ["FAKE_DETERMINISTIC_CLASSIFICATION"],
        }
        result = {
            "schema_version": self.identity.schema_version,
            "stage": stage,
            "request_id": deterministic_id(
                "semantic_test_request",
                [stage, integrity_hash(safe_request)],
            ),
            "items": [],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        if stage in {"STRUCTURAL_ANALYSIS", "SIMPLE_HISTORICAL_COMBINED", "POETRY_SIRA_EXTRACTION"}:
            result["structure"] = structure
        if stage in {"SIMPLE_HISTORICAL_COMBINED", "POETRY_SIRA_EXTRACTION"}:
            result.update({
                "entities": [], "events": [], "relations": [],
                "claims": [], "isnads": [], "temporals": [],
                "institutions": [],
            })
        return result

    def classify_structure(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._result("STRUCTURAL_ANALYSIS", request)

    def extract_mentions(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._result("MENTION_EXTRACTION", request)

    def extract_combined(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._result("SIMPLE_HISTORICAL_COMBINED", request)

    def extract_events_relations(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return self._result("EVENT_RELATION_EXTRACTION", request)

    def extract_claims_attribution(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return self._result("CLAIM_ATTRIBUTION", request)

    def extract_isnad(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._result("ISNAD_EXTRACTION", request)

    def extract_poetry_sira(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._result("POETRY_SIRA_EXTRACTION", request)

    def extract_critical_route(
        self,
        route: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return self._result(f"CRITICAL_{route}", request)

    def verify_evidence(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._result("MODEL_EVIDENCE_REVIEW", request)

    def critique_extraction(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._result("CRITICAL_REVIEW", request)

    def unload(self) -> dict[str, Any]:
        self.unloaded = True
        return {
            "status": "UNLOADED",
            "provider_id": self.identity.provider_id,
            "model_id": self.identity.model_id,
        }


__all__ = [
    "DeterministicSemanticTestProvider",
    "SemanticExtractionProvider",
]
