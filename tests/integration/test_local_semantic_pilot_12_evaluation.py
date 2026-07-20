from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

from src.application.cli_v2 import build_parser
from src.application.local_semantic_intelligence import (
    ADJUDICATION_CATEGORIES,
    DeterministicSemanticTestProvider,
    PilotAdjudicationError,
    PilotAdjudicationStore,
    PilotEvaluationError,
    PilotQuickReviewStore,
    QuickReviewError,
    QUICK_COMPLETED,
    QUICK_PENDING,
    build_pilot_workbench_server,
    evaluate_pilot_12,
    pilot_12_status,
    prepare_pilot_12_evaluation,
    prepare_quick_review,
    quick_evaluate,
    quick_update,
    run_real_model_pilot_12,
)
from src.application.local_semantic_intelligence.ollama_provider import (
    _compact_prior_stage_outputs,
    _critic_prior_summary,
    _ollama_http_error_code,
)
from src.application.local_semantic_intelligence.semantic_prompts import (
    schema_for_stage,
)
from src.application.local_semantic_intelligence.validation import (
    canonicalize_literal_spans,
)
from src.application.local_semantic_intelligence.pilot_view_models import (
    build_presentation_view,
)
from src.application.local_semantic_intelligence.pilot_workbench import (
    _ui_html,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _current(
    number: int,
    *,
    entities: int = 0,
    events: int = 0,
    relations: int = 0,
    claims: int = 0,
    temporal: int = 0,
    isnad: int = 0,
) -> dict:
    return {
        "audit_segment_id": f"audit-{number:02d}",
        "source_id": "source-test",
        "segment_id": number,
        "locator": f"shamela://test/book/1?segment_id={number}",
        "entities": [
            {"mention_id": f"m-{number}-{index}"}
            for index in range(entities)
        ],
        "events": [
            {"event_mention_id": f"e-{number}-{index}", "event_type": "EVENT"}
            for index in range(events)
        ],
        "relations": [
            {"relation_id": f"r-{number}-{index}"}
            for index in range(relations)
        ],
        "claims": [
            {"claim_id": f"c-{number}-{index}"}
            for index in range(claims)
        ],
        "temporal_mentions": [
            {"temporal_id": f"t-{number}-{index}"}
            for index in range(temporal)
        ],
        "isnad_chains": [
            {"chain_id": f"i-{number}-{index}"}
            for index in range(isnad)
        ],
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    audit = tmp_path / "working" / "shamela-extraction-quality-audit"
    semantic = tmp_path / "working" / "local-semantic-intelligence"
    specs = [
        (1, 5, "أسماء المدلسين", "إبراهيم بن يزيد", _current(1, entities=2), ["MULTIPLE_ENTITY_MENTIONS"]),
        (2, 400, "الحوادث", "عزل الوزير ورتب عوضه كاتباً", _current(2, entities=2, events=1, claims=1), []),
        (3, 5, "أسماء المدلسين", "حدثنا زيد عن عمرو", _current(3, entities=2, isnad=1), ["CURRENT_ISNAD_CHAIN"]),
        (4, 619, "السيرة", "أيا دار عبلة في المساء", _current(4, entities=1), []),
        (5, 400, "الحوادث", "دخل الوزير المدرسة النظامية", _current(5, entities=2), []),
        (6, 405, "فضائل مصر", "وقع ذلك بعد سنة من الحادث", _current(6, temporal=1), ["TEMPORAL_EXPRESSION"]),
        (7, 5, "أسماء المدلسين", "<span data-type='title'>عنوان</span>", _current(7), ["HEADING_BEARING_SEGMENT"]),
        (8, 151020, "جهد القريحة", "الحد طريق التصور والقياس طريق التصديق", _current(8), ["NEGATIVE_CONTROL_NO_CURRENT_SIGNAL"]),
        (9, 400, "الحوادث", "وصل الأمير ثم توفي القاضي", _current(9, entities=2, events=2, claims=2), []),
        (10, 405, "فضائل مصر", "زيد وعمرو وبكر من أهل مصر", _current(10, entities=3, relations=1), []),
        (11, 400, "الحوادث", "وفيها توفي محمد بن يحيى.", _current(11, entities=1, events=1), []),
        (
            12,
            400,
            "الحوادث",
            ("وصل الأمير إلى بغداد ثم عزل الوزير. " * 70),
            _current(12, entities=4, events=3, relations=2, claims=2, temporal=1),
            ["LONG_DENSE_SEGMENT"],
        ),
    ]
    annotations = []
    manifest = []
    for number, book_id, title, text, current, reasons in specs:
        annotations.append(
            {
                "annotation_id": f"gold-{number}",
                "audit_segment_id": f"audit-{number:02d}",
                "book_id": book_id,
                "book_title": title,
                "source_id": "source-test",
                "segment_id": number,
                "locator": current["locator"],
                "original_text": text,
                "current_extraction": current,
                "reviewer_notes": "ملاحظة تشخيصية فقط",
                "expected_entities": [{"must_not_leak": True}],
            }
        )
        manifest.append(
            {
                "audit_segment_id": f"audit-{number:02d}",
                "selection_reasons": reasons,
            }
        )
    _write_json(
        audit / "gold-annotation-template.json",
        {"schema_version": "test-gold", "annotations": annotations},
    )
    _write_json(
        audit / "audit-sample-manifest.json",
        {"segments": manifest},
    )
    return audit, semantic


def _complete_patch(annotation: dict) -> dict:
    return {
        "structural_type_gold": "NON_HISTORICAL",
        "gold_entities": [],
        "gold_events": [],
        "gold_relations": [],
        "gold_temporal_mentions": [],
        "gold_isnad": [],
        "gold_claims_attribution": [],
        "explicitly_absent": {
            category: True
            for category in ADJUDICATION_CATEGORIES
            if category != "structure"
        },
        "category_review": {
            category: "REVIEWED"
            for category in ADJUDICATION_CATEGORIES
        },
        "adjudication_status": "COMPLETED",
        "model_output_judgments": [],
        "baseline_output_judgments": [],
        "reviewer_notes": "",
        "expert_review_resolution": {
            "status": "UNRESOLVED",
            "reason": "",
        },
    }


def test_selection_is_deterministic_complete_and_does_not_leak_gold(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    first = prepare_pilot_12_evaluation(semantic, audit_root=audit)
    manifest_path = (
        semantic / "pilot-12" / "pilot-12-selection-manifest.json"
    )
    first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    second = prepare_pilot_12_evaluation(semantic, audit_root=audit)
    second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert first["pilot_id"] == second["pilot_id"]
    assert first_manifest == second_manifest
    assert first["sample_count"] == 12
    assert all(first["coverage"].values())
    assert all(
        "expected_entities"
        not in (
            semantic / "pilot-12" / item["input_artifact"]
        ).read_text(encoding="utf-8")
        for item in first_manifest["segments"]
    )


def test_fake_benchmark_writes_auditable_artifacts_and_no_graph(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    result = run_real_model_pilot_12(
        semantic,
        DeterministicSemanticTestProvider(),
        audit_root=audit,
    )
    assert result["completed_segments"] == 12
    assert result["failed_segments"] == 0
    assert result["maximum_parallel_model_requests"] == 1
    assert result["knowledge_graph_written"] is False
    assert result["recorded_pilot_model_calls"] == result["total_model_calls"]
    assert result["recorded_pilot_model_calls"] > 0
    assert result["pilot_model_output_limits"] == {
        "entities_per_segment": 12,
        "events_per_segment": 2,
        "relations_per_segment": 3,
        "institutions_per_segment": 2,
        "claims_per_segment": 2,
        "isnads_per_segment": 2,
        "temporal_mentions_per_segment": 3,
        "critic_issues_per_segment": 12,
        "quality_effect": "BOUNDED_RECALL_REQUIRES_HUMAN_ADJUDICATION",
        "scope": "LOW_MEMORY_PILOT_ONLY",
    }
    assert not (semantic / "pilot-12" / "knowledge-graph").exists()
    for item in result["segments"]:
        root = (
            semantic
            / "pilot-12"
            / "segments"
            / item["audit_segment_id"]
        )
        assert (root / "parsed-semantic-v2.json").is_file()
        assert (root / "deterministic-validation.json").is_file()
        assert (root / "baseline-rule-extraction.json").is_file()
        assert (root / "performance.json").is_file()


def test_completed_segments_resume_without_model_calls(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    first_provider = DeterministicSemanticTestProvider()
    first_result = run_real_model_pilot_12(
        semantic,
        first_provider,
        audit_root=audit,
    )
    second_provider = DeterministicSemanticTestProvider()
    result = run_real_model_pilot_12(
        semantic,
        second_provider,
        audit_root=audit,
    )
    assert result["total_model_calls"] == 0
    assert (
        result["recorded_pilot_model_calls"]
        == first_result["recorded_pilot_model_calls"]
    )
    assert len(result["resumed_segments"]) == 12
    assert second_provider.calls == []


def test_stale_process_lock_is_archived_before_resume(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    prepared = prepare_pilot_12_evaluation(
        semantic,
        audit_root=audit,
    )
    root = Path(prepared["pilot_root"])
    _write_json(
        root / ".pilot-12-benchmark.lock",
        {
            "schema_version": "siraj-local-semantic-pilot-evaluation-v1",
            "pid": 2_147_483_000,
            "mode": "SEQUENTIAL_LOCAL_MODEL_RUN",
            "pilot_id": prepared["pilot_id"],
        },
    )
    result = run_real_model_pilot_12(
        semantic,
        DeterministicSemanticTestProvider(),
        audit_root=audit,
    )
    assert result["completed_segments"] == 12
    assert not (root / ".pilot-12-benchmark.lock").exists()
    assert len(list((root / "stale-locks").glob("*.json"))) == 1


def test_interrupted_benchmark_preserves_failure_and_can_resume(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    failing = DeterministicSemanticTestProvider(
        fail_stage="SIMPLE_HISTORICAL_COMBINED"
    )
    first = run_real_model_pilot_12(
        semantic,
        failing,
        audit_root=audit,
    )
    assert first["failed_segments"] > 0
    assert first["status"] == "REAL_MODEL_PILOT_12_INCOMPLETE"
    recovered = run_real_model_pilot_12(
        semantic,
        DeterministicSemanticTestProvider(),
        audit_root=audit,
    )
    assert recovered["completed_segments"] == 12
    assert recovered["failed_segments"] == 0


def test_adjudication_immutability_spans_backups_undo_and_completion_gate(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    prepare_pilot_12_evaluation(semantic, audit_root=audit)
    store = PilotAdjudicationStore(semantic)
    annotation = store.load()["annotations"][0]
    with pytest.raises(PilotAdjudicationError, match="IMMUTABLE"):
        store.update(
            annotation["annotation_id"],
            {"original_text": "معدل"},
        )
    with pytest.raises(PilotAdjudicationError, match="COMPLETION"):
        store.update(
            annotation["annotation_id"],
            {"adjudication_status": "COMPLETED"},
        )
    result = store.update(
        annotation["annotation_id"],
        {
            "reviewer_notes": "مراجعة أولى",
            "adjudication_status": "IN_PROGRESS",
        },
    )
    assert result["backup_file"].endswith("000001.json")
    assert store.load()["annotations"][0]["reviewer_notes"] == "مراجعة أولى"
    assert store.undo_last()["status"] == "UNDONE"
    assert store.load()["annotations"][0]["reviewer_notes"] == ""
    with pytest.raises(PilotAdjudicationError, match="SPAN_OUT_OF_RANGE"):
        store.update(
            annotation["annotation_id"],
            {
                "gold_entities": [
                    {
                        "start": 0,
                        "end": 99999,
                        "exact_surface": "خطأ",
                        "type": "PERSON",
                    }
                ]
            },
        )


def test_evaluator_blocked_until_every_category_is_resolved(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    run_real_model_pilot_12(
        semantic,
        DeterministicSemanticTestProvider(),
        audit_root=audit,
    )
    with pytest.raises(PilotEvaluationError, match="COMPLETED"):
        evaluate_pilot_12(semantic)
    store = PilotAdjudicationStore(semantic)
    for annotation in store.load()["annotations"]:
        store.update(
            annotation["annotation_id"],
            _complete_patch(annotation),
        )
    result = evaluate_pilot_12(semantic)
    assert result["status"] == "VALID_REAL_MODEL_PILOT_12_EVALUATED"
    assert result["safety"]["knowledge_graph_written"] is False


def test_workbench_is_loopback_only_and_exposes_offline_state(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    prepare_pilot_12_evaluation(semantic, audit_root=audit)
    with pytest.raises(PilotAdjudicationError, match="LOCALHOST_ONLY"):
        build_pilot_workbench_server(
            semantic,
            host="0.0.0.0",
        )
    server = build_pilot_workbench_server(semantic, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/state",
            timeout=3,
        ) as response:
            state = json.loads(response.read().decode("utf-8"))
        assert state["ai_calls_allowed"] is False
        assert state["external_network_allowed"] is False
        assert state["progress"]["pending"] == 12
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_presentation_view_models_are_human_readable_and_read_only() -> None:
    annotation = {
        "gold_entities": [],
        "gold_events": [],
        "gold_relations": [],
        "gold_temporal_mentions": [],
        "gold_isnad": [],
        "gold_claims_attribution": [],
        "segment_id": "segment-1",
        "source_id": "source-1",
        "locator": "shamela://test/1",
    }
    comparison = {
        "baseline": {},
        "model_raw": {
            "mentions": {
                "entities": [
                    {
                        "mention_id": "m-1",
                        "exact_surface": "عبد الله بن طاهر",
                        "entity_types": ["PERSON"],
                        "contextual_roles": ["RULER"],
                        "evidence": {"text": "عبد الله بن طاهر"},
                    },
                    {
                        "mention_id": "m-2",
                        "exact_surface": "بغداد",
                        "entity_types": ["CITY"],
                        "contextual_roles": ["LOCATION"],
                        "evidence": {"text": "بغداد"},
                    },
                ]
            },
            "events_relations": {
                "events": [
                    {
                        "event_id": "e-1",
                        "event_type": "ARRIVAL",
                        "evidence": {"text": "قدم عبد الله بن طاهر بغداد"},
                        "participants": [
                            {"mention_reference": "m-1", "role": "ARRIVER"}
                        ],
                        "places": [
                            {"mention_reference": "m-2", "role": "DESTINATION"}
                        ],
                    }
                ],
                "relations": [
                    {
                        "relation_id": "r-1",
                        "subject_mention": "m-1",
                        "relation_type": "NARRATED_FROM",
                        "object_mention": "m-2",
                        "evidence": {"text": "روى"},
                        "explicit_or_inferred": "EXPLICIT",
                    }
                ],
            },
            "claims_attribution": {
                "isnads": [
                    {
                        "chain_id": "i-1",
                        "narrators": ["زيد", "عمرو", "بكر"],
                        "exact_chain_range": {"text": "زيد عن عمرو عن بكر"},
                    }
                ],
                "temporals": [],
                "claims": [],
            },
        },
        "reconciliation": {
            "items": [
                {
                    "item_id": "m-1",
                    "status": "ACCEPTED_HIGH_CONFIDENCE",
                    "reason_codes": [],
                }
            ]
        },
        "validation": {"issues": []},
        "rejected_elements": {"items": []},
        "warnings": {"items": []},
    }
    before = json.dumps(comparison, sort_keys=True)
    view = build_presentation_view(annotation, comparison)
    reconciled = view["tabs"]["reconciled"]["categories"]
    entities = next(item for item in reconciled if item["key"] == "entities")
    events = next(item for item in reconciled if item["key"] == "events")
    relations = next(item for item in reconciled if item["key"] == "relations")
    isnad = next(item for item in reconciled if item["key"] == "isnad")
    assert entities["items"][0]["types"] == ["شخص"]
    assert events["items"][0]["participants"][0]["name"] == "عبد الله بن طاهر"
    assert events["items"][0]["places"][0]["role"] == "وجهة"
    assert "— روى عن —" in relations["items"][0]["sentence"]
    assert isnad["items"][0]["narrators"] == ["زيد", "عمرو", "بكر"]
    assert json.dumps(comparison, sort_keys=True) == before


def test_default_workbench_html_hides_raw_json_and_technical_identity() -> None:
    html = _ui_html()
    assert 'id="baseline"' not in html
    assert 'id="model"' not in html
    assert 'id="reconciled"' not in html
    assert "النتيجة بعد التحقق والمصالحة" in html
    assert "عرض التفاصيل التقنية" in html
    assert "dir=\"rtl\"" in html
    assert "source_id" not in html.split("<body>", 1)[1].split(
        "عرض التفاصيل التقنية",
        1,
    )[0]


def test_read_only_presentation_does_not_change_adjudication_file(
    tmp_path: Path,
) -> None:
    audit, semantic = _fixture(tmp_path)
    prepare_pilot_12_evaluation(semantic, audit_root=audit)
    store = PilotAdjudicationStore(semantic)
    before = store.path.read_bytes()
    state = store.state()
    assert state["presentation_contract"]["default_tab"] == "reconciled"
    assert store.path.read_bytes() == before


def test_cli_surface_contains_pilot_commands() -> None:
    parser = build_parser()
    benchmark = parser.parse_args(
        [
            "semantic",
            "local",
            "benchmark",
            "--semantic-root",
            "C:/semantic",
            "--config",
            "C:/semantic/config.json",
            "--sample",
            "pilot-12",
        ]
    )
    assert benchmark.semantic_action == "benchmark"
    status = parser.parse_args(
        [
            "semantic",
            "local",
            "pilot-status",
            "--semantic-root",
            "C:/semantic",
            "--sample",
            "pilot-12",
        ]
    )
    assert status.semantic_action == "pilot-status"
    review = parser.parse_args(
        [
            "semantic",
            "local",
            "pilot-review",
            "status",
            "--semantic-root",
            "C:/semantic",
            "--sample",
            "pilot-12",
        ]
    )
    assert review.pilot_review_action == "status"
    quick_serve = parser.parse_args(
        [
            "semantic", "local", "pilot-review", "serve",
            "--semantic-root", "C:/semantic", "--sample", "pilot-12",
        ]
    )
    assert quick_serve.mode == "quick"
    quick_status = parser.parse_args(
        [
            "semantic", "local", "pilot-review", "quick-status",
            "--semantic-root", "C:/semantic", "--sample", "pilot-12",
        ]
    )
    assert quick_status.pilot_review_action == "quick-status"


def test_quick_review_is_independent_and_has_completion_gate(tmp_path: Path) -> None:
    audit, semantic = _fixture(tmp_path)
    prepare_pilot_12_evaluation(semantic, audit_root=audit)
    detailed = PilotAdjudicationStore(semantic)
    detailed_before = detailed.path.read_bytes()
    quick = prepare_quick_review(semantic)
    assert len(quick["records"]) == 12
    assert PilotQuickReviewStore(semantic).progress()["pending"] == 12
    record_id = quick["records"][0]["annotation_id"]
    result = quick_update(
        semantic, record_id, judgment="PARTIAL",
        error_categories=["WRONG_BOUNDARY"], notes="ملاحظة سريعة",
    )
    assert result["status"] == "SAVED"
    state = PilotQuickReviewStore(semantic).load()
    assert state["records"][0]["quick_status"] == QUICK_COMPLETED
    assert detailed.path.read_bytes() == detailed_before
    assert list((semantic / "pilot-12" / "quick-review-backups").glob("*.json"))
    with pytest.raises(QuickReviewError, match="QUICK_EVALUATION_REQUIRES_ALL_12_COMPLETED"):
        quick_evaluate(semantic)


def test_quick_workbench_has_no_technical_default_view(tmp_path: Path) -> None:
    _audit, semantic = _fixture(tmp_path)
    prepare_pilot_12_evaluation(semantic, audit_root=_audit)
    server = build_pilot_workbench_server(semantic, port=0, mode="quick")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=3) as response:
            html = response.read().decode("utf-8")
        assert "GOOD" in html
        assert "PARTIAL" in html
        assert "NEEDS_CONTEXT" in html
        assert "/api/record/" in html
        assert "raw model output" not in html.lower()
        assert "JSON الخام" not in html
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_ollama_context_limit_error_is_normalized_without_raw_text() -> None:
    raw = json.dumps(
        {
            "error": json.dumps(
                {
                    "error": {
                        "code": 400,
                        "message": (
                            "request (1608 tokens) exceeds the available "
                            "context size (1536 tokens), try increasing it"
                        ),
                        "type": "exceed_context_size_error",
                    }
                }
            )
        }
    ).encode("utf-8")
    assert (
        _ollama_http_error_code(400, raw)
        == "OLLAMA_CONTEXT_LIMIT_EXCEEDED"
    )


def test_structural_ranges_are_compact_and_literal_text_is_derived() -> None:
    schema = schema_for_stage("STRUCTURAL_ANALYSIS")
    ranges = schema["properties"]["structure"]["properties"][
        "prose_ranges"
    ]
    assert ranges["maxItems"] == 8
    assert "text" not in ranges["items"]["properties"]
    normalized, reason_codes = canonicalize_literal_spans(
        {
            "structure": {
                "heading_ranges": [{"start": 0, "end": 5}],
            }
        },
        "بغداد مدينة",
    )
    assert (
        normalized["structure"]["heading_ranges"][0]["text"]
        == "بغداد"
    )
    assert "STRUCTURAL_RANGE_TEXT_DERIVED" in reason_codes


def test_model_items_are_compact_then_enriched_deterministically() -> None:
    entity_schema = schema_for_stage("MENTION_EXTRACTION")[
        "properties"
    ]["entities"]
    assert entity_schema["maxItems"] == 12
    entity_schema = entity_schema["items"]
    assert (
        schema_for_stage("EVENT_RELATION_EXTRACTION")["properties"][
            "events"
        ]["maxItems"]
        == 2
    )
    assert (
        schema_for_stage("CLAIM_ATTRIBUTION")["properties"]["claims"][
            "maxItems"
        ]
        == 2
    )
    assert "mention_id" not in entity_schema["properties"]
    assert "source_id" not in entity_schema["properties"]
    assert "locator" not in entity_schema["properties"]
    payload = {
        "entities": [
            {
                "exact_surface": "بغداد",
                "start": 0,
                "end": 5,
                "entity_types": ["CITY"],
                "contextual_roles": ["LOCATION"],
                "uncertainty": "NONE",
            }
        ]
    }
    first, _ = canonicalize_literal_spans(
        payload,
        "بغداد مدينة",
        "source-1",
        "shamela://test",
    )
    second, _ = canonicalize_literal_spans(
        payload,
        "بغداد مدينة",
        "source-1",
        "shamela://test",
    )
    assert first == second
    entity = first["entities"][0]
    assert entity["mention_id"].startswith("semantic_entity_")
    assert entity["source_id"] == "source-1"
    assert entity["locator"] == "shamela://test"
    assert entity["evidence"] == {
        "start": 0,
        "end": 5,
        "text": "بغداد",
    }


def test_prior_stage_prompt_context_excludes_repeated_audit_payloads() -> None:
    compact = _compact_prior_stage_outputs(
        {
            "structure": {
                "prose_ranges": [
                    {"start": 0, "end": 5, "text": "بغداد"}
                ],
                "provider_metadata": {"tokens": {"input": 99}},
                "safe_raw_provider_response": {
                    "message": {"content": "raw"}
                },
            },
            "mentions": {
                "entities": [
                    {
                        "mention_id": "m1",
                        "exact_surface": "بغداد",
                        "source_id": "source-1",
                        "locator": "shamela://test",
                    }
                ]
            },
        }
    )
    structure = compact["structure"]
    assert "provider_metadata" not in structure
    assert "safe_raw_provider_response" not in structure
    assert structure["prose_ranges"][0] == {"start": 0, "end": 5}
    entity = compact["mentions"]["entities"][0]
    assert entity["mention_id"] == "m1"
    assert "source_id" not in entity
    assert "locator" not in entity


def test_critic_context_contains_only_bounded_semantic_summaries() -> None:
    summary = _critic_prior_summary(
        {
            "structure": {"prose_ranges": [{"start": 0, "end": 20}]},
            "mentions": {
                "entities": [
                    {
                        "mention_id": "m1",
                        "exact_surface": "بغداد",
                        "start": 0,
                        "end": 5,
                        "entity_types": ["CITY"],
                        "contextual_roles": ["LOCATION"],
                        "provider_metadata": {"raw": "excluded"},
                    }
                ]
            },
            "validation": {
                "issues": [{"code": "TEST", "subject_id": "m1"}]
            },
        }
    )
    assert "structure" not in summary
    assert summary["validation"]["issues"][0]["code"] == "TEST"
    entity = summary["mentions"]["entities"][0]
    assert entity["mention_id"] == "m1"
    assert "provider_metadata" not in entity
