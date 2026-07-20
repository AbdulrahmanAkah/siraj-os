from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import socket

import pytest

from src.application import cli_v2
from src.application.local_semantic_intelligence import (
    DeterministicSemanticTestProvider,
    LocalSemanticOrchestrator,
    OllamaLocalSemanticConfig,
    OllamaLocalSemanticProvider,
    ProviderIdentity,
    SemanticProviderHealth,
    SemanticProviderError,
    SemanticSegmentInput,
    initialize_semantic_foundation,
    select_pilot_12,
    load_provider_config,
    run_semantic_segment,
    canonicalize_literal_spans,
    validate_semantic_outputs,
)
from src.application.local_semantic_intelligence.ollama_provider import (
    serialize_json_utf8,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _segment(
    number: int = 1,
    text: str = "عزل الخليفة الوزير بعد سنة من تعيينه.",
) -> SemanticSegmentInput:
    return SemanticSegmentInput(
        audit_segment_id=f"audit-{number:02d}",
        source_id="source-1",
        locator=f"shamela://local/test/book/1?segment_id={number}",
        original_text=text,
        book_id=400,
        book_title="كتاب التاريخ",
        segment_id=number,
        current_extraction={
            "entities": [],
            "events": [],
            "relations": [],
            "claims": [],
            "temporal_mentions": [],
            "isnad_chains": [],
        },
        reviewer_notes="حدود الاسم تحتاج مراجعة",
        selection_reasons=["ENTITY_BOUNDARY_FAILURE"],
    )


def _gold_fixture(root: Path) -> tuple[Path, Path]:
    audit = root / "audit"
    output = root / "semantic"
    annotations = []
    manifest_segments = []
    for number in range(1, 14):
        book_id = 619 if number == 4 else 400
        current = {
            "audit_segment_id": f"audit-{number:02d}",
            "source_id": "source-1",
            "segment_id": number,
            "locator": (
                f"shamela://local/test/book/{book_id}?segment_id={number}"
            ),
            "entities": (
                [
                    {
                        "mention_id": f"mention-{number}",
                        "original_text_span": {
                            "start": 0,
                            "end": 4,
                            "text": "محمد",
                        },
                    }
                ]
                if number in {1, 2, 3}
                else []
            ),
            "events": (
                [{"event_type": "APPOINTMENT_EVENT"}]
                if number == 2
                else []
            ),
            "relations": [],
            "claims": (
                [{"claim_id": "claim-office", "predicate": "RULED"}]
                if number == 5
                else []
            ),
            "temporal_mentions": (
                [{"temporal_type": "RELATIVE"}]
                if number == 6
                else []
            ),
            "isnad_chains": (
                [{"chain_id": "chain-1"}]
                if number == 3
                else []
            ),
        }
        annotation = {
            "annotation_id": f"annotation-{number:02d}",
            "audit_segment_id": f"audit-{number:02d}",
            "book_id": book_id,
            "book_title": "السيرة" if book_id == 619 else "التاريخ",
            "source_id": "source-1",
            "segment_id": number,
            "locator": current["locator"],
            "original_text": "محمد في بغداد بعد سنة.",
            "current_extraction": current,
            "expected_entities": [{"secret_gold_label": number}],
            "expected_events": [],
            "expected_relations": [],
            "expected_temporal_mentions": [],
            "expected_isnad": [],
            "explicitly_absent_items": [],
            "reviewer_status": "COMPLETED",
            "reviewer_notes": "ملاحظة بشرية" if number <= 6 else "",
        }
        reasons = []
        if number == 3:
            reasons.append("CURRENT_ISNAD_CHAIN")
        if number == 4:
            reasons.append("POETRY_OR_SHORT_LINE_STRUCTURE")
        if number == 6:
            reasons.append("TEMPORAL_EXPRESSION")
        if number == 7:
            reasons.append("NEGATIVE_CONTROL_NO_CURRENT_SIGNAL")
        if number == 8:
            reasons.append("HEADING_BEARING_SEGMENT")
        annotations.append(annotation)
        manifest_segments.append(
            {
                "audit_segment_id": annotation["audit_segment_id"],
                "selection_reasons": reasons,
            }
        )
    _write_json(
        audit / "gold-annotation-template.json",
        {"annotations": annotations},
    )
    _write_json(
        audit / "audit-sample-manifest.json",
        {"segments": manifest_segments},
    )
    return audit, output


def test_ollama_local_only_policy_rejects_non_loopback() -> None:
    with pytest.raises(ValueError, match="LOOPBACK"):
        OllamaLocalSemanticConfig(
            endpoint="http://example.com:11434",
            model_reference="custom-model",
        )
    config = OllamaLocalSemanticConfig(
        endpoint="http://localhost:11434",
        model_reference="custom-model",
    )
    assert config.hardware.concurrency == 1
    assert config.temperature == 0
    assert config.stream is False


def test_utf8_serialization_preserves_arabic_without_bom() -> None:
    text = "عبد الله بن طاهر قدم بغداد، ثم ولي خراسان."
    payload = {"text": text, "diacritized": "عَبْدُ اللهِ"}
    encoded = serialize_json_utf8(payload)
    assert not encoded.startswith(b"\xef\xbb\xbf")
    assert json.loads(encoded.decode("utf-8")) == payload
    assert "عبد الله".encode("utf-8") in encoded


def test_corrupt_arabic_provider_output_is_rejected() -> None:
    def transport(_method: str, _url: str, _payload: dict | None, _timeouts: dict[str, float]):
        return {"message": {"content": '{"structure":{"segment_type":"???"}}'}}

    provider = OllamaLocalSemanticProvider(
        OllamaLocalSemanticConfig(model_reference="qwen3:4b-instruct"),
        transport=transport,
    )
    with pytest.raises(SemanticProviderError, match="CORRUPT_UTF8"):
        provider.classify_structure(
            {"source_id": "s", "locator": "l", "original_text": "بغداد"}
        )


def test_ollama_request_is_structured_local_and_unload_is_explicit() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def transport(method: str, url: str, payload: dict | None, _timeouts: dict[str, float]):
        calls.append((method, url, payload))
        if url.endswith("/api/chat") and payload and payload.get("messages"):
            return {
                "message": {"content": json.dumps({
                    "structure": {
                        "segment_type": "HISTORICAL_NARRATIVE",
                        "subtypes": [], "heading_ranges": [], "prose_ranges": [],
                        "poetry_ranges": [], "isnad_ranges": [], "matn_ranges": [],
                        "footnote_ranges": [], "quoted_source_ranges": [],
                        "requires_previous_context": False,
                        "requires_next_context": False,
                        "confidence": 1, "rationale_codes": ["TEST"],
                    }
                })},
                "prompt_eval_count": 10,
                "eval_count": 4,
            }
        return {}

    provider = OllamaLocalSemanticProvider(
        OllamaLocalSemanticConfig(model_reference="custom-local-model"),
        transport=transport,
    )
    result = provider.classify_structure(
        {
            "source_id": "source",
            "locator": "shamela://test",
            "original_text": "نص عربي",
        }
    )
    assert result["provider_metadata"]["provider_id"] == "OLLAMA_LOCAL_SEMANTIC"
    assert result["provider_metadata"]["raw_response_retained"] is True
    assert "authorization" not in result["safe_raw_provider_response"]
    assert calls[0][1].endswith("/api/chat")
    assert calls[0][2]["stream"] is False
    assert calls[0][2]["think"] is False
    assert isinstance(calls[0][2]["format"], dict)
    assert calls[0][2]["messages"][0]["role"] == "system"
    assert "untrusted_source_data" in calls[0][2]["messages"][1]["content"]
    assert calls[0][1].startswith("http://127.0.0.1:11434/")
    assert provider.unload()["status"] == "UNLOADED"
    assert calls[-1][2]["keep_alive"] == 0


def test_exact_evidence_validation_and_reference_integrity() -> None:
    text = "عزل الخليفة الوزير."
    valid_span = {"start": 0, "end": 3, "text": "عزل"}
    outputs = {
        "structure": {"structure": {"heading_ranges": []}},
        "mentions": {
            "entities": [
                {
                    "mention_id": "m1",
                    "exact_surface": "الخليفة",
                    "start": 4,
                    "end": 11,
                    "evidence": {
                        "start": 4,
                        "end": 11,
                        "text": "الخليفة",
                    },
                    "source_id": "source",
                    "locator": "loc",
                }
            ]
        },
        "events_relations": {
            "events": [
                {
                    "event_id": "e1",
                    "trigger": valid_span,
                    "participants": [{"mention_id": "m1", "role": "ACTOR"}],
                    "source_id": "source",
                    "locator": "loc",
                }
            ],
            "relations": [],
            "institutions": [],
        },
        "claims_attribution": {
            "claims": [],
            "isnads": [],
            "temporals": [],
        },
    }
    valid = validate_semantic_outputs(text, "source", "loc", outputs)
    assert valid["status"] == "VALID"
    outputs["events_relations"]["events"][0]["trigger"]["text"] = "ولد"
    invalid = validate_semantic_outputs(text, "source", "loc", outputs)
    assert invalid["status"] == "INVALID"
    assert "EVIDENCE_TEXT_MISMATCH" in {
        item["code"] for item in invalid["issues"]
    }


def test_unique_literal_evidence_offsets_are_derived_before_validation() -> None:
    text = "\u0630\u0643\u0631 \u0625\u0633\u0645\u0627\u0639\u064a\u0644 \u0628\u0646 \u0625\u0633\u062d\u0627\u0642"
    payload, reasons = canonicalize_literal_spans(
        {
            "structure": {
                "heading_ranges": [
                    {"start": 999, "end": 1000, "text": "\u0625\u0633\u0645\u0627\u0639\u064a\u0644 \u0628\u0646 \u0625\u0633\u062d\u0627\u0642"}
                ]
            }
        },
        text,
    )
    span = payload["structure"]["heading_ranges"][0]
    assert text[span["start"] : span["end"]] == span["text"]
    assert reasons == ["LITERAL_EVIDENCE_OFFSET_DERIVED"]


def test_event_role_validation_rejects_external_participant_and_place() -> None:
    text = "قدم عبد الله بن طاهر إلى بغداد."
    actor = "عبد الله بن طاهر"
    place = "بغداد"
    actor_start = text.index(actor)
    place_start = text.index(place)
    outputs = {
        "structure": {"structure": {"heading_ranges": []}},
        "mentions": {"entities": [
            {"mention_id": "m1", "exact_surface": actor, "start": actor_start,
             "end": actor_start + len(actor), "evidence": {"start": actor_start, "end": actor_start + len(actor), "text": actor},
             "source_id": "source", "locator": "loc"},
            {"mention_id": "m2", "exact_surface": place, "start": place_start,
             "end": place_start + len(place), "evidence": {"start": place_start, "end": place_start + len(place), "text": place},
             "source_id": "source", "locator": "loc"},
        ]},
        "events_relations": {"events": [{
            "event_id": "arrival", "trigger": {"start": 0, "end": 3, "text": "قدم"},
            "evidence": {"start": 0, "end": len(text), "text": text},
            "participants": [{"mention_reference": "m1", "exact_surface": actor, "role": "ARRIVER"}],
            "places": [{"mention_reference": "m2", "exact_surface": place, "role": "DESTINATION"}],
            "source_id": "source", "locator": "loc",
        }], "relations": [], "institutions": []},
        "claims_attribution": {"claims": [], "isnads": [], "temporals": []},
    }
    assert validate_semantic_outputs(text, "source", "loc", outputs)["status"] == "VALID"
    outputs["events_relations"]["events"][0]["places"][0]["exact_surface"] = "خراسان"
    invalid = validate_semantic_outputs(text, "source", "loc", outputs)
    assert "EVENT_PLACE_NOT_LITERAL" in {item["code"] for item in invalid["issues"]}


def test_orchestrator_is_resumable_and_cache_deterministic(tmp_path: Path) -> None:
    provider = DeterministicSemanticTestProvider()
    orchestrator = LocalSemanticOrchestrator(provider, tmp_path)
    first = orchestrator.run_segment(_segment())
    calls_after_first = list(provider.calls)
    second = orchestrator.run_segment(_segment())
    assert first["run_id"] == second["run_id"]
    assert second["cache_hits"] > 0
    assert provider.calls == calls_after_first
    assert second["graph_written"] is False
    assert not (tmp_path / "knowledge-graph").exists()


def test_failed_stage_checkpoint_can_resume(tmp_path: Path) -> None:
    provider = DeterministicSemanticTestProvider(
        fail_stage="SIMPLE_HISTORICAL_COMBINED"
    )
    orchestrator = LocalSemanticOrchestrator(provider, tmp_path)
    with pytest.raises(RuntimeError, match="SIMPLE_HISTORICAL_COMBINED"):
        orchestrator.run_segment(_segment())
    failure = json.loads(
        (
            tmp_path
            / "segments"
            / "audit-01"
            / "01-structural_analysis.json"
        ).read_text(encoding="utf-8")
    )
    assert failure["status"] == "FAILED"
    provider.fail_stage = None
    assert orchestrator.run_segment(_segment())["status"] == "COMPLETED"


def test_non_historical_segment_short_circuits_extraction(tmp_path: Path) -> None:
    provider = DeterministicSemanticTestProvider(
        {
            "STRUCTURAL_ANALYSIS": {
                "schema_version": "siraj-local-semantic-v2",
                "structure": {
                    "segment_type": "NON_HISTORICAL",
                    "subtypes": [],
                    "heading_ranges": [],
                    "prose_ranges": [],
                    "poetry_ranges": [],
                    "isnad_ranges": [],
                    "matn_ranges": [],
                    "footnote_ranges": [],
                    "quoted_source_ranges": [],
                    "requires_previous_context": False,
                    "requires_next_context": False,
                    "confidence": 1.0,
                    "rationale_codes": ["NEGATIVE_CONTROL"],
                },
            }
        }
    )
    result = LocalSemanticOrchestrator(provider, tmp_path).run_segment(
        replace(
            _segment(text="فهرس المحتويات"),
            selection_reasons=["NEGATIVE_CONTROL"],
        )
    )
    assert result["route"] == "SHORT_CIRCUIT_NON_HISTORICAL"
    assert "MENTION_EXTRACTION" not in provider.calls
    checkpoint = json.loads(
        (
            tmp_path
            / "segments"
            / "audit-01"
            / "02-mention_extraction.json"
        ).read_text(encoding="utf-8")
    )
    assert checkpoint["status"] == "SKIPPED"


def test_pilot_selection_and_foundation_do_not_leak_expected_labels(
    tmp_path: Path,
) -> None:
    audit, output = _gold_fixture(tmp_path)
    gold = json.loads(
        (audit / "gold-annotation-template.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (audit / "audit-sample-manifest.json").read_text(encoding="utf-8")
    )
    first = select_pilot_12(gold, manifest)
    second = select_pilot_12(gold, manifest)
    assert [item["audit_segment_id"] for item in first] == [
        item["audit_segment_id"] for item in second
    ]
    result = initialize_semantic_foundation(audit, output)
    assert result["sample_count"] == 12
    payloads = list((output / "segments").glob("*/segment-input.json"))
    assert len(payloads) == 12
    assert all("expected_entities" not in path.read_text(encoding="utf-8") for path in payloads)
    validation = json.loads(
        (output / "validation-report.json").read_text(encoding="utf-8")
    )
    assert validation["gold_annotations_modified"] is False
    assert validation["knowledge_graph_written"] is False


def test_fake_provider_path_uses_no_network_or_shamela(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = tmp_path / "shamela4" / "marker"
    marker.parent.mkdir()
    marker.write_bytes(b"unchanged")
    before = (marker.read_bytes(), marker.stat().st_mtime_ns)

    def deny_network(*_args, **_kwargs):
        raise AssertionError("external network forbidden")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    LocalSemanticOrchestrator(
        DeterministicSemanticTestProvider(),
        tmp_path / "outputs",
    ).run_segment(_segment())
    assert (marker.read_bytes(), marker.stat().st_mtime_ns) == before


def test_cli_reports_unavailable_ollama_without_raw_failure(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    audit, output = _gold_fixture(tmp_path)
    initialize_semantic_foundation(audit, output)

    class UnavailableProvider:
        identity = ProviderIdentity("OLLAMA_LOCAL_SEMANTIC", "missing")

        def health_check(self):
            return SemanticProviderHealth(
                "UNAVAILABLE",
                self.identity,
                "OLLAMA_UNAVAILABLE",
            )

    monkeypatch.setattr(
        cli_v2,
        "build_ollama_provider",
        lambda _path: UnavailableProvider(),
    )
    exit_code = cli_v2.main(
        [
            "--json",
            "semantic",
            "local",
            "status",
            "--semantic-root",
            str(output.resolve()),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 5
    assert payload["status"] == "DEPENDENCY_FAILURE"
    assert payload["error"] == "OLLAMA_UNAVAILABLE"


def test_fake_provider_unload_is_explicit() -> None:
    provider = DeterministicSemanticTestProvider()
    result = provider.unload()
    assert result["status"] == "UNLOADED"
    assert provider.unloaded is True


@pytest.mark.skipif(
    os.environ.get("SIRAJ_RUN_LOCAL_MODEL_TESTS") != "1",
    reason="set SIRAJ_RUN_LOCAL_MODEL_TESTS=1 for an explicit Ollama localhost test",
)
def test_optional_local_qwen_single_segment() -> None:
    root = Path(r"C:\SIRAJ\Workspace\first-project\working\local-semantic-intelligence")
    config_path = root / "provider-config.example.json"
    provider = OllamaLocalSemanticProvider(load_provider_config(config_path))
    if provider.health_check().status != "AVAILABLE":
        pytest.skip("qwen3:4b-instruct is not locally available")
    result = run_semantic_segment(
        root,
        provider,
        "shamela_quality_audit_segment_7977f9842198b9a8",
    )
    assert result["graph_written"] is False
