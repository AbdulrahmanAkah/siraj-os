from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.cli_v2 import build_parser, command_semantic_cloud_gemini_schema_check
from src.application.local_semantic_intelligence import (
    GeminiSemanticConfig,
    GeminiSemanticProvider,
    run_gemini_critical_4,
    estimate_gemini_cost,
)
from src.application.local_semantic_intelligence.gemini_provider import (
    GEMINI_PROMPT_VERSION,
    GEMINI_PROVIDER_ID,
    GoogleGenAITransport,
    redact_sensitive,
    run_gemini_schema_check,
)
from src.application.local_semantic_intelligence.gemini_schema import (
    CRITICAL_ROUTES,
    gemini_schema_for_route,
)
from src.application.local_semantic_intelligence.models import SemanticProviderError


class FakeGeminiTransport:
    api_host = "generativelanguage.googleapis.com"

    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate_content(self, *, model: str, contents: str, config: dict) -> object:
        self.calls.append({"model": model, "contents": contents, "config": config})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _response(payload: dict, *, tokens: int = 11) -> dict:
    return {
        "text": json.dumps(payload, ensure_ascii=False),
        "finish_reason": "STOP",
        "response_id": "safe-request-id",
        "usage_metadata": {
            "prompt_token_count": tokens,
            "candidates_token_count": 7,
            "cached_content_token_count": 2,
        },
    }


def _provider(transport: FakeGeminiTransport, **changes: object) -> GeminiSemanticProvider:
    config_values: dict[str, object] = {
        "external_network_allowed": True,
        "data_policy_acknowledged": True,
        # Most unit tests supply an exact deterministic response sequence
        # for one model. Disable production fallback models by default so
        # the expected primary error is not replaced by ALL_MODELS_FAILED.
        "fallback_models": (),
        # Offline tests may intentionally exercise retries. Keep the test
        # budget above those deterministic transport calls without changing
        # production defaults.
        "maximum_requests_per_run": 64,
        "maximum_input_tokens_per_run": 100_000,
        "maximum_output_tokens_per_run": 20_000,
    }
    config_values.update(changes)

    config = GeminiSemanticConfig(
        **config_values,
    )
    return GeminiSemanticProvider(config, api_key_getter=lambda: "AIza-secret-value", transport=transport)


def _span(text: str, surface: str) -> dict:
    start = text.index(surface)
    return {"start": start, "end": start + len(surface), "text": surface}


def _entity(text: str, surface: str) -> dict:
    return {"id": "m1", "surface": surface, "types": ["PERSON"], "roles": [], "evidence": _span(text, surface), "name_boundary_complete": True, "explicit_proper_name": True}




def test_gemini_prompt_version_is_explicit_and_versioned() -> None:
    assert GEMINI_PROMPT_VERSION == "gemini-critical-prompts-v2"
    assert GEMINI_PROMPT_VERSION.startswith(
        "gemini-critical-prompts-v"
    )



def test_test_provider_uses_isolated_budget_limits() -> None:
    provider = _provider(FakeGeminiTransport([]))

    assert provider.config.fallback_models == ()
    assert provider.config.maximum_requests_per_run == 64
    assert provider.config.maximum_input_tokens_per_run == 100_000
    assert provider.config.maximum_output_tokens_per_run == 20_000

def test_missing_key_is_explicit_and_redacted() -> None:
    provider = GeminiSemanticProvider(GeminiSemanticConfig(external_network_allowed=True, data_policy_acknowledged=True), api_key_getter=lambda: None, transport=FakeGeminiTransport([]))
    assert provider.health_check().reason_code == "GEMINI_API_KEY_MISSING"
    assert redact_sensitive({"api_key": "AIza-secret-value", "note": "AIza-secret-value"}, "AIza-secret-value") == {"api_key": "[REDACTED]", "note": "[REDACTED]"}


def test_structured_arabic_request_and_usage_parsing() -> None:
    text = "إسماعيل بن أبي يحيى وصفه أحمد بالتدليس"
    transport = FakeGeminiTransport([_response({"route": "PERSON_AND_STATUS", "entities": [_entity(text, "إسماعيل بن أبي يحيى")], "statuses": [], "relations": []})])
    result = _provider(transport).extract_critical_route("PERSON_AND_STATUS", {"source_id": "s", "locator": "l", "original_text": text, "route": "PERSON_AND_STATUS"})
    assert "إسماعيل بن أبي يحيى" in transport.calls[0]["contents"]
    assert transport.calls[0]["config"]["response_mime_type"] == "application/json"
    assert transport.calls[0]["config"]["response_schema"]
    assert "response_json_schema" not in transport.calls[0]["config"]
    assert result["provider_metadata"]["usage"]["total_tokens"] == 18
    assert result["provider_metadata"]["finish_reason"] == "STOP"
    assert "AIza-secret-value" not in json.dumps(result, ensure_ascii=False)


def test_official_transport_builds_typed_generate_content_config() -> None:
    captured: dict[str, object] = {}

    class TypedConfig:
        def __init__(self, **kwargs: object):
            captured["config"] = kwargs

    class ThinkingConfig:
        def __init__(self, **kwargs: object):
            captured["thinking"] = kwargs

    class Models:
        def generate_content(self, **kwargs: object) -> object:
            captured["request"] = kwargs
            return {"text": "{}"}

    transport = object.__new__(GoogleGenAITransport)
    transport._types = type("Types", (), {"GenerateContentConfig": TypedConfig, "ThinkingConfig": ThinkingConfig})
    transport._client = type("Client", (), {"models": Models()})()
    transport.generate_content(
        model="gemini-3.5-flash", contents="Arabic UTF-8: بغداد",
        config={"temperature": 0, "max_output_tokens": 128, "response_mime_type": "application/json", "response_schema": {"type": "object"}, "thinking_level": "low"},
    )
    assert "response_schema" in captured["config"]
    assert "response_json_schema" not in captured["config"]
    assert captured["thinking"] == {"thinking_level": "low"}


def test_empty_malformed_safety_auth_and_timeout_mapping() -> None:
    text = "حبيب بن أبي ثابت"
    base = {"source_id": "s", "locator": "l", "original_text": text, "route": "PERSON_AND_STATUS"}
    with pytest.raises(SemanticProviderError, match="GEMINI_FINISH_REASON_FAILURE"):
        _provider(FakeGeminiTransport([{"text": None, "finish_reason": "MAX_TOKENS"}])).extract_critical_route("PERSON_AND_STATUS", base)
    with pytest.raises(SemanticProviderError, match="GEMINI_EMPTY_RESPONSE"):
        _provider(FakeGeminiTransport([{"text": None, "finish_reason": "STOP"}])).extract_critical_route("PERSON_AND_STATUS", base)
    with pytest.raises(SemanticProviderError, match="GEMINI_JSON_PARSE_FAILED"):
        _provider(FakeGeminiTransport([{"text": "{broken", "finish_reason": "STOP"}])).extract_critical_route("PERSON_AND_STATUS", base)
    with pytest.raises(SemanticProviderError, match="GEMINI_RESPONSE_SCHEMA_MISMATCH"):
        _provider(FakeGeminiTransport([_response({"route": "PERSON_AND_STATUS", "entities": []})])).extract_critical_route("PERSON_AND_STATUS", base)
    with pytest.raises(SemanticProviderError, match="GEMINI_SAFETY_BLOCK"):
        _provider(FakeGeminiTransport([RuntimeError("safety blocked")])).extract_critical_route("PERSON_AND_STATUS", base)
    with pytest.raises(SemanticProviderError, match="GEMINI_AUTH_FAILED"):
        _provider(FakeGeminiTransport([RuntimeError("authentication failure")])).extract_critical_route("PERSON_AND_STATUS", base)
    quota_transport = FakeGeminiTransport([RuntimeError("quota exceeded")])
    with pytest.raises(SemanticProviderError, match="GEMINI_QUOTA_EXCEEDED"):
        _provider(quota_transport, retries=1).extract_critical_route("PERSON_AND_STATUS", base)
    assert len(quota_transport.calls) == 1
    good = _response({"route": "PERSON_AND_STATUS", "entities": [_entity(text, text)], "statuses": [], "relations": []})
    transport = FakeGeminiTransport([TimeoutError("timeout"), good])
    result = _provider(transport, retries=1).extract_critical_route("PERSON_AND_STATUS", base)
    assert result["provider_metadata"]["retry_count"] == 1
    assert len(transport.calls) == 2


def _critical_fixture(root: Path) -> tuple[Path, dict[str, str]]:
    semantic = root / "semantic"
    texts = {3: "إسماعيل بن أبي يحيى وصفه أحمد بالتدليس", 8: "حدثنا الأعمش عن حبيب بن أبي ثابت قال الخبر", 15: "هاشم قد آلت له سقاية", 17: "ولي محمد بن يحيى تدريس المدرسة النظامية"}
    annotations = [{"audit_segment_id": f"audit-{segment}", "segment_id": segment, "source_id": "source", "locator": f"shamela://{segment}", "book_title": "test", "original_text": text, "prior_diagnostic_reviewer_notes": "diagnostic"} for segment, text in texts.items()]
    root_path = semantic / "pilot-12"
    root_path.mkdir(parents=True)
    (root_path / "pilot-12-human-adjudication.json").write_text(json.dumps({"annotations": annotations}, ensure_ascii=False), encoding="utf-8")
    (root_path / "pilot-12-run-manifest.json").write_text(json.dumps({"segments": [{"audit_segment_id": f"audit-{segment}"} for segment in texts]}, ensure_ascii=False), encoding="utf-8")
    for name in ("pilot-12-quick-review-summary.json", "pilot-12-validation-report.json", "pilot-12-reconciliation-report.json", "pilot-12-learning-report.json"):
        (root_path / name).write_text("{}", encoding="utf-8")
    return semantic, texts


def test_gemini_critical_4_artifacts_checkpoint_and_no_graph(tmp_path: Path) -> None:
    semantic, texts = _critical_fixture(tmp_path)
    responses = [
        _response({"route": "PERSON_AND_STATUS", "entities": [_entity(texts[3], "إسماعيل بن أبي يحيى")], "statuses": [], "relations": []}),
        _response({"route": "ISNAD", "entities": [_entity(texts[8], "الأعمش"), _entity(texts[8], "حبيب بن أبي ثابت")], "isnads": [{"narrators": ["الأعمش", "حبيب بن أبي ثابت"], "evidence": _span(texts[8], "الأعمش عن حبيب بن أبي ثابت"), "matn_boundary": texts[8].index("قال") }]}),
        _response({"route": "SIRA_POETRY", "entities": [_entity(texts[15], "هاشم")], "events": [{"type": "OFFICE", "explicit": True, "evidence": _span(texts[15], "آلت له سقاية")}]}),
        _response({"route": "APPOINTMENT_AND_OFFICE", "entities": [_entity(texts[17], "محمد بن يحيى")], "appointments": [{"kind": "APPOINTMENT", "appointee": "محمد بن يحيى", "appointing_authority": "", "office": "تدريس المدرسة النظامية", "jurisdiction": "", "generic_object": "", "evidence": _span(texts[17], texts[17])}]}),
    ]
    result = run_gemini_critical_4(semantic, _provider(FakeGeminiTransport(responses)))
    output = semantic / "pilot-12" / "critical-4"
    assert result["provider_id"] == GEMINI_PROVIDER_ID
    assert (output / "gemini-critical-4-comparison.json").is_file()
    assert (output / "gemini-critical-4-run-manifest.json").is_file()
    assert not (semantic / "knowledge-graph").exists()


def test_cloud_cli_surface_is_provider_explicit() -> None:
    args = build_parser().parse_args(["semantic", "cloud", "critical-regression", "run", "--semantic-root", "C:/semantic", "--sample", "critical-4", "--provider", "gemini", "--config", "C:/safe/config.json"])
    assert args.semantic_scope == "cloud"
    assert args.provider == "gemini"
    schema = build_parser().parse_args(["semantic", "cloud", "gemini", "schema-check", "--config", "C:/safe/config.json"])
    assert schema.gemini_action == "schema-check"
    probe = build_parser().parse_args(["semantic", "cloud", "gemini", "probe", "--config", "C:/safe/config.json", "--route", "PERSON_AND_STATUS"])
    assert probe.route == "PERSON_AND_STATUS"


def _keywords(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keywords(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_keywords(item) for item in value)) if value else set()
    return set()


def test_gemini_route_schemas_are_sanitized_and_round_trip_offline(tmp_path: Path) -> None:
    for route in CRITICAL_ROUTES:
        schema = gemini_schema_for_route(route)
        assert not ({"additionalProperties", "minLength", "maxItems", "minimum", "anyOf", "$ref", "$defs"} & _keywords(schema))
    report = run_gemini_schema_check(tmp_path)
    assert report["status"] == "PASS"
    assert (tmp_path / "gemini-schema-check-report.json").is_file()


def test_schema_check_cli_never_requires_key_or_transport(tmp_path: Path) -> None:
    config = tmp_path / "gemini-config.json"
    config.write_text(json.dumps({"provider": {}, "hardware": {}, "budget_limits": {}}, ensure_ascii=False), encoding="utf-8")
    result = command_semantic_cloud_gemini_schema_check(str(config), "critical-4")
    assert result["status"] == "SUCCESS"
    assert result["data"]["network_called"] is False
    assert (tmp_path / "gemini-schema-check-report.json").is_file()


def test_api_schema_rejection_records_safe_failure_artifact(tmp_path: Path) -> None:
    semantic, _texts = _critical_fixture(tmp_path)

    class SchemaRejected(RuntimeError):
        status_code = 400
        code = "INVALID_ARGUMENT"

    provider = _provider(FakeGeminiTransport([SchemaRejected("response_schema contains unsupported additionalProperties AIza-secret-value")]))
    with pytest.raises(SemanticProviderError, match="GEMINI_REQUEST_SCHEMA_REJECTED"):
        run_gemini_critical_4(semantic, provider)
    artifact = semantic / "pilot-12" / "critical-4" / "gemini-critical-4-last-failure.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["diagnostic"]["failure_stage"] == "REQUEST_SCHEMA_REJECTED"
    assert "AIza-secret-value" not in json.dumps(payload, ensure_ascii=False)


def test_evidence_failure_is_not_mislabeled_as_schema_failure(tmp_path: Path) -> None:
    semantic, texts = _critical_fixture(tmp_path)
    bad = {
        "route": "PERSON_AND_STATUS",
        "entities": [{
            **_entity(texts[3], texts[3].split()[0]),
            "evidence": {"start": 0, "end": 1, "text": "x"},
        }],
        "statuses": [],
        "relations": [],
    }
    transport = FakeGeminiTransport([
        # Critical-03 initial output and repair output:
        # both intentionally fail evidence validation.
        _response(bad),
        _response(bad),

        # Critical-08: valid isnad output so the complete
        # Critical-4 run can continue deterministically.
        _response({
            "route": "ISNAD",
            "entities": [
                _entity(texts[8], "الأعمش"),
                {
                    **_entity(
                        texts[8],
                        "حبيب بن أبي ثابت",
                    ),
                    "id": "m2",
                },
            ],
            "isnads": [
                {
                    "narrators": [
                        "الأعمش",
                        "حبيب بن أبي ثابت",
                    ],
                    "evidence": _span(
                        texts[8],
                        "الأعمش عن حبيب بن أبي ثابت",
                    ),
                    "matn_boundary": texts[8].index("قال"),
                }
            ],
        }),

        # Critical-15: valid explicit office event.
        _response({
            "route": "SIRA_POETRY",
            "entities": [
                _entity(texts[15], "هاشم"),
            ],
            "events": [
                {
                    "type": "OFFICE",
                    "explicit": True,
                    "evidence": _span(
                        texts[15],
                        "آلت له سقاية",
                    ),
                }
            ],
        }),

        # Critical-17: valid appointment output.
        _response({
            "route": "APPOINTMENT_AND_OFFICE",
            "entities": [
                _entity(
                    texts[17],
                    "محمد بن يحيى",
                ),
            ],
            "appointments": [
                {
                    "kind": "APPOINTMENT",
                    "appointee": "محمد بن يحيى",
                    "appointing_authority": "",
                    "office": "تدريس المدرسة النظامية",
                    "jurisdiction": "",
                    "generic_object": "",
                    "evidence": _span(
                        texts[17],
                        texts[17],
                    ),
                }
            ],
        }),
    ])

    provider = _provider(transport)
    result = run_gemini_critical_4(semantic, provider)

    assert len(transport.calls) == 5
    assert result["status"] == "COMPLETED_WITH_CASE_FAILURES"
    payload = json.loads((semantic / "pilot-12" / "critical-4" / "gemini-critical-4-last-failure.json").read_text(encoding="utf-8"))
    assert payload["diagnostic"]["failure_stage"] == "EVIDENCE_VALIDATION_FAILED"
    assert payload["diagnostic"]["error_code"] == "GEMINI_EVIDENCE_VALIDATION_FAILED"


def test_cost_estimation_requires_explicit_versioned_price_table() -> None:
    usage = {"input_tokens": 100, "output_tokens": 50, "cached_tokens": 10}
    assert estimate_gemini_cost(model_reference="gemini-3.5-flash", usage=usage, price_table=None)["cost_status"] == "UNKNOWN"
    estimate = estimate_gemini_cost(
        model_reference="gemini-3.5-flash", usage=usage,
        price_table={"schema_version": "siraj-gemini-cost-table-v1", "models": {"gemini-3.5-flash": {"input_per_million": "1", "output_per_million": "2", "cached_per_million": "0.5", "currency": "USD"}}},
    )
    assert estimate["cost_status"] == "ESTIMATED"
