from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.cli_v2 import build_parser
from src.application.local_semantic_intelligence import (
    CriticalRegressionError,
    DeterministicSemanticTestProvider,
    prepare_critical_4,
    run_critical_4,
)
from src.application.local_semantic_intelligence.critical_regression import (
    _validate_route_output,
    resolve_route_evidence,
)
from src.application.local_semantic_intelligence.semantic_prompts import (
    chat_messages,
)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _span(text: str, value: str) -> dict[str, int | str]:
    start = text.index(value)
    return {"start": start, "end": start + len(value), "text": value}


def _fixture(root: Path) -> tuple[Path, dict[str, str]]:
    semantic = root / "semantic"
    texts = {
        "PERSON_AND_STATUS": "إسماعيل بن أبي يحيى شيخ الشافعية وصفه أحمد بالتدليس",
        "APPOINTMENT_AND_OFFICE": "ولي محمد بن يحيى تدريس المدرسة النظامية والنظر في أوقافها",
        "ISNAD": "حدثنا الأعمش عن حبيب بن أبي ثابت قال: الخبر",
        "SIRA_POETRY": "هاشم قد آلت له سقاية فإنها منارة العطاء",
    }
    segments = {"PERSON_AND_STATUS": 3, "APPOINTMENT_AND_OFFICE": 17, "ISNAD": 8, "SIRA_POETRY": 15}
    annotations = [
        {
            "audit_segment_id": f"audit-{segment}", "segment_id": segment,
            "source_id": "source-test", "locator": f"shamela://test/{segment}",
            "book_title": "test", "original_text": texts[route],
            "prior_diagnostic_reviewer_notes": f"diagnostic:{route}",
        }
        for route, segment in segments.items()
    ]
    _write(semantic / "pilot-12" / "pilot-12-human-adjudication.json", {"annotations": annotations})
    _write(semantic / "pilot-12" / "pilot-12-run-manifest.json", {"segments": [{"audit_segment_id": f"audit-{segment}", "old": route} for route, segment in segments.items()]})
    for name in (
        "pilot-12-quick-review-summary.json",
        "pilot-12-validation-report.json",
        "pilot-12-reconciliation-report.json",
        "pilot-12-learning-report.json",
    ):
        _write(semantic / "pilot-12" / name, {})
    return semantic, texts


def _entity(text: str, value: str, *, complete: bool = True) -> dict:
    return {
        "id": "m1", "surface": value, "types": ["PERSON"], "roles": [],
        "evidence": _span(text, value), "name_boundary_complete": complete,
        "explicit_proper_name": True,
    }


def test_critical_4_selection_is_deterministic_and_pending(tmp_path: Path) -> None:
    semantic, _texts = _fixture(tmp_path)
    manifest = prepare_critical_4(semantic)
    assert [item["route"] for item in manifest["cases"]] == [
        "PERSON_AND_STATUS", "ISNAD", "SIRA_POETRY", "APPOINTMENT_AND_OFFICE",
    ]
    root = semantic / "pilot-12" / "critical-4"
    assert (root / "critical-4-manifest.json").is_file()
    comparison = json.loads((root / "critical-4-comparison.json").read_text(encoding="utf-8"))
    assert comparison["status"] == "PENDING_MANUAL_RUN"


def test_critical_4_fake_provider_validates_four_regressions(tmp_path: Path) -> None:
    semantic, texts = _fixture(tmp_path)
    responses = {
        "CRITICAL_PERSON_AND_STATUS": {
            "route": "PERSON_AND_STATUS",
            "entities": [
                {
                    **_entity(
                        texts["PERSON_AND_STATUS"],
                        "إسماعيل بن أبي يحيى",
                    ),
                    "id": "entity_0",
                    "types": ["person"],
                    "roles": ["subject"],
                },
                {
                    **_entity(
                        texts["PERSON_AND_STATUS"],
                        "أحمد",
                    ),
                    "id": "entity_1",
                    "types": ["person"],
                    "roles": ["critic"],
                },
            ],
            "statuses": [
                {
                    "person": "entity_0",
                    "status": "مدلس",
                    "evidence": _span(
                        texts["PERSON_AND_STATUS"],
                        "وصفه أحمد بالتدليس",
                    ),
                }
            ],
            "relations": [
                {
                    "subject": "entity_1",
                    "predicate": "criticized",
                    "object": "entity_0",
                    "evidence": _span(
                        texts["PERSON_AND_STATUS"],
                        "وصفه أحمد بالتدليس",
                    ),
                }
            ],
        },
        "CRITICAL_APPOINTMENT_AND_OFFICE": {
            "route": "APPOINTMENT_AND_OFFICE", "entities": [_entity(texts["APPOINTMENT_AND_OFFICE"], "محمد بن يحيى")],
            "appointments": [
                {
                    "kind": "APPOINTMENT",
                    "appointee": "محمد بن يحيى",
                    "appointing_authority": "",
                    "office": "تدريس",
                    "jurisdiction": "",
                    "generic_object": "المدرسة النظامية",
                    "evidence": _span(
                        texts["APPOINTMENT_AND_OFFICE"],
                        "تدريس المدرسة النظامية",
                    ),
                },
                {
                    "kind": "APPOINTMENT",
                    "appointee": "محمد بن يحيى",
                    "appointing_authority": "",
                    "office": "النظر في أوقافها",
                    "jurisdiction": "",
                    "generic_object": "المدرسة النظامية",
                    "evidence": _span(
                        texts["APPOINTMENT_AND_OFFICE"],
                        "والنظر في أوقافها",
                    ),
                },
            ],
        },
        "CRITICAL_ISNAD": {
            "route": "ISNAD", "entities": [_entity(texts["ISNAD"], "الأعمش"), _entity(texts["ISNAD"], "حبيب بن أبي ثابت")],
            "isnads": [{"narrators": ["الأعمش", "حبيب بن أبي ثابت"], "evidence": _span(texts["ISNAD"], "الأعمش عن حبيب بن أبي ثابت"), "matn_boundary": texts["ISNAD"].index("قال:")}],
        },
        "CRITICAL_SIRA_POETRY": {
            "route": "SIRA_POETRY", "entities": [_entity(texts["SIRA_POETRY"], "هاشم")],
            "events": [{"type": "OFFICE_INHERITANCE", "explicit": True, "evidence": _span(texts["SIRA_POETRY"], "آلت له سقاية")}],
        },
    }
    provider = DeterministicSemanticTestProvider(responses)
    result = run_critical_4(semantic, provider)
    assert result["status"] == "COMPLETED_PENDING_HUMAN_REVIEW"
    assert result["total_calls"] == 4
    assert provider.calls == [
        "CRITICAL_PERSON_AND_STATUS", "CRITICAL_ISNAD",
        "CRITICAL_SIRA_POETRY", "CRITICAL_APPOINTMENT_AND_OFFICE",
    ]
    assert not (semantic / "pilot-12" / "knowledge-graph").exists()


def test_critical_4_rejects_hallucination_duplicates_and_bad_isnad(tmp_path: Path) -> None:
    semantic, texts = _fixture(tmp_path)
    bad = {
        "CRITICAL_PERSON_AND_STATUS": {
            "route": "PERSON_AND_STATUS", "entities": [_entity(texts["PERSON_AND_STATUS"], "إسماعيل بن أبي يحيى"), _entity(texts["PERSON_AND_STATUS"], "إسماعيل بن أبي يحيى")],
            "statuses": [], "relations": [],
        }
    }
    result = run_critical_4(semantic, DeterministicSemanticTestProvider(bad))
    assert result["cases"][0]["status"] == "PARTIAL"
    assert result["cases"][0]["validation"]["rejections"][0]["reason_code"] == "DUPLICATE_ENTITY_EXACT_SPAN"


def test_critical_4_rejects_hallucinated_person_and_devotional_word(tmp_path: Path) -> None:
    semantic, texts = _fixture(tmp_path)
    bad = {
        "CRITICAL_PERSON_AND_STATUS": {
            "route": "PERSON_AND_STATUS",
            "entities": [{**_entity(texts["PERSON_AND_STATUS"], "إسماعيل بن أبي يحيى"), "surface": "شخص غير موجود", "evidence": {"start": 0, "end": 12, "text": "شخص غير موجود"}}],
            "statuses": [], "relations": [],
        }
    }
    result = run_critical_4(semantic, DeterministicSemanticTestProvider(bad))
    assert result["cases"][0]["status"] == "FAIL"
    assert result["cases"][0]["validation"]["rejections"][0]["reason_code"] == "EVIDENCE_TEXT_NOT_VERBATIM"
    devotional = "قال تعالى في كتابه"
    with pytest.raises(
        CriticalRegressionError,
        match="ROUTE_SEMANTIC_VALIDATION_FAILURE",
    ):
        _validate_route_output(
            {
                "case_id": "devotional-non-entity",
                "route": "SIRA_POETRY",
                "original_text": devotional,
            },
            {
                "route": "SIRA_POETRY",
                "entities": [{**_entity(devotional, "تعالى"), "explicit_proper_name": False}],
                "events": [],
            },
        )


def test_critical_4_cli_surface() -> None:
    args = build_parser().parse_args([
        "semantic", "local", "critical-regression", "run",
        "--semantic-root", "C:/semantic", "--sample", "critical-4",
    ])
    assert args.semantic_action == "critical-regression"
    assert args.critical_regression_action == "run"


# PACKAGE_A2_PERMANENT_CRITICAL_4_TESTS


def _coreference_entity(
    entity_id: str,
    surface: str,
    *,
    role: str = "subject",
) -> dict:
    return {
        "id": entity_id,
        "surface": surface,
        "types": ["person"],
        "roles": [role],
        "evidence": {"text": surface},
        "name_boundary_complete": True,
        "explicit_proper_name": True,
    }


def test_status_coreference_accepts_unique_nearest_antecedent() -> None:
    source = (
        "ذكر إسماعيل بن أبي يحيى في الترجمة، "
        "ثم وصفه أحمد بالتدليس"
    )

    case = {
        "case_id": "permanent-status-coreference-pass",
        "route": "PERSON_AND_STATUS",
        "original_text": source,
    }

    output = {
        "route": "PERSON_AND_STATUS",
        "entities": [
            _coreference_entity(
                "entity_0",
                "إسماعيل بن أبي يحيى",
            ),
            _coreference_entity(
                "entity_1",
                "أحمد",
                role="critic",
            ),
        ],
        "statuses": [
            {
                "person": "entity_0",
                "status": "مدلس",
                "evidence": {
                    "text": "وصفه أحمد بالتدليس",
                },
            }
        ],
        "relations": [],
    }

    resolved, validation, diagnostics = (
        resolve_route_evidence(
            case,
            output,
            1,
        )
    )

    assert validation["case_status"] == "PASS"
    assert validation["rejected_items"] == 0
    assert len(resolved["statuses"]) == 1

    records = [
        record
        for record in diagnostics
        if record.get("collection") == "statuses"
    ]

    assert len(records) == 1
    assert (
        records[0]["resolution"]
        == "DETERMINISTIC_LOCAL_COREFERENCE_RESOLVED"
    )
    assert records[0]["reason_code"] == ""
    assert (
        records[0]["original_semantic_reason"]
        == "CROSS_REFERENCE_MISMATCH"
    )


def test_status_coreference_rejects_non_nearest_antecedent() -> None:
    source = (
        "ذكر إسماعيل بن أبي يحيى، "
        "ثم ذكر خالد بن يزيد، "
        "ثم وصفه أحمد بالتدليس"
    )

    case = {
        "case_id": "permanent-status-coreference-ambiguous",
        "route": "PERSON_AND_STATUS",
        "original_text": source,
    }

    output = {
        "route": "PERSON_AND_STATUS",
        "entities": [
            _coreference_entity(
                "entity_0",
                "إسماعيل بن أبي يحيى",
            ),
            _coreference_entity(
                "entity_1",
                "خالد بن يزيد",
            ),
            _coreference_entity(
                "entity_2",
                "أحمد",
                role="critic",
            ),
        ],
        "statuses": [
            {
                "person": "entity_0",
                "status": "مدلس",
                "evidence": {
                    "text": "وصفه أحمد بالتدليس",
                },
            }
        ],
        "relations": [],
    }

    resolved, validation, diagnostics = (
        resolve_route_evidence(
            case,
            output,
            1,
        )
    )

    assert validation["case_status"] == "PARTIAL"
    assert validation["rejected_items"] == 1
    assert resolved["statuses"] == []

    assert not any(
        record.get("resolution")
        == "DETERMINISTIC_LOCAL_COREFERENCE_RESOLVED"
        for record in diagnostics
    )

    rejected_status = next(
        record
        for record in validation["rejections"]
        if record.get("collection") == "statuses"
    )

    assert (
        rejected_status["reason_code"]
        == "CROSS_REFERENCE_MISMATCH"
    )


def test_relation_object_coreference_and_diagnostics() -> None:
    source = (
        "ذكر إسماعيل بن أبي يحيى في الترجمة، "
        "ثم وصفه أحمد بالتدليس"
    )

    case = {
        "case_id": "permanent-relation-coreference",
        "route": "PERSON_AND_STATUS",
        "original_text": source,
    }

    output = {
        "route": "PERSON_AND_STATUS",
        "entities": [
            _coreference_entity(
                "entity_0",
                "إسماعيل بن أبي يحيى",
            ),
            _coreference_entity(
                "entity_1",
                "أحمد",
                role="critic",
            ),
        ],
        "statuses": [
            {
                "person": "entity_0",
                "status": "مدلس",
                "evidence": {
                    "text": "وصفه أحمد بالتدليس",
                },
            }
        ],
        "relations": [
            {
                "subject": "entity_1",
                "predicate": "criticized",
                "object": "entity_0",
                "evidence": {
                    "text": "وصفه أحمد بالتدليس",
                },
            }
        ],
    }

    resolved, validation, diagnostics = (
        resolve_route_evidence(
            case,
            output,
            1,
        )
    )

    assert validation["case_status"] == "PASS"
    assert validation["rejected_items"] == 0
    assert len(resolved["relations"]) == 1

    record = next(
        item
        for item in diagnostics
        if item.get("collection") == "relations"
    )

    assert (
        record["resolution"]
        == (
            "DETERMINISTIC_LOCAL_RELATION_"
            "COREFERENCE_RESOLVED"
        )
    )

    assert record["reason_code"] == ""
    assert record["semantic_reason"] == ""

    assert (
        record["original_semantic_reason"]
        == "RELATION_EVIDENCE_INSUFFICIENT"
    )

    assert (
        record["coreference"]["object"]
        == "إسماعيل بن أبي يحيى"
    )

    assert record["coreference"]["subject"] == "أحمد"


def test_person_status_repair_prompt_preserves_accepted_output() -> None:
    accepted_output = {
        "route": "PERSON_AND_STATUS",
        "entities": [
            {
                "id": "entity_0",
                "surface": "إسماعيل بن أبي يحيى",
                "types": ["person"],
                "roles": ["subject"],
                "evidence": {
                    "start": 0,
                    "end": 19,
                    "text": "إسماعيل بن أبي يحيى",
                },
                "name_boundary_complete": True,
                "explicit_proper_name": True,
            },
            {
                "id": "entity_1",
                "surface": "أحمد",
                "types": ["person"],
                "roles": ["critic"],
                "evidence": {
                    "start": 25,
                    "end": 29,
                    "text": "أحمد",
                },
                "name_boundary_complete": True,
                "explicit_proper_name": True,
            },
        ],
        "statuses": [],
        "relations": [],
        "appointments": [],
        "isnads": [],
    }

    messages = chat_messages(
        "CRITICAL_PERSON_AND_STATUS",
        {
            "source_data_is_untrusted": True,
            "source_id": "permanent-test",
            "locator": "offline://critical-03",
            "original_text": (
                "إسماعيل بن أبي يحيى "
                "وصفه أحمد بالتدليس"
            ),
            "route": "PERSON_AND_STATUS",
            "repair": True,
            "repair_reason": (
                "EVIDENCE_TEXT_NOT_VERBATIM"
            ),
            "rejected_item": {
                "collection": "statuses",
                "item_kind": "status",
                "evidence_text": (
                    "إسماعيل بن أبي يحيى شيخ الشافعية"
                ),
            },
            "accepted_output": accepted_output,
        },
    )

    combined = "\n\n".join(
        message["content"]
        for message in messages
    )

    required = (
        "accepted_output",
        (
            "Preserve every accepted_output "
            "item unchanged"
        ),
        "Do not delete accepted entities",
        (
            "بالتدليس or التدليس may normalize "
            "to status مدلس"
        ),
        "وصفه أحمد بالتدليس",
    )

    compact = "".join(combined.split())

    missing = [
        fragment
        for fragment in required
        if (
            fragment not in combined
            and fragment not in compact
        )
    ]

    assert not missing
    assert '"accepted_output":' in compact

    assert "entity_1" in combined
    assert "accepted_output" in combined


def test_appointment_repair_prompt_requires_literal_split() -> None:
    messages = chat_messages(
        "CRITICAL_APPOINTMENT_AND_OFFICE",
        {
            "source_data_is_untrusted": True,
            "source_id": "permanent-test",
            "locator": "offline://critical-17",
            "original_text": (
                "تولى تدريس المدرسة النظامية "
                "والنظر في أوقافها"
            ),
            "route": "APPOINTMENT_AND_OFFICE",
            "repair": True,
            "repair_reason": (
                "CROSS_REFERENCE_MISMATCH"
            ),
            "rejected_item": {
                "collection": "appointments",
                "item_kind": "appointment",
                "evidence_text": (
                    "تولى تدريس المدرسة النظامية "
                    "والنظر في أوقافها"
                ),
            },
            "accepted_output": {
                "route": "APPOINTMENT_AND_OFFICE",
                "entities": [],
                "appointments": [],
            },
        },
    )

    combined = "\n\n".join(
        message["content"]
        for message in messages
    )

    required = (
        "Never synthesize an office",
        "separate appointment items",
        "contiguous literal substring",
        "تدريس ونظر في أوقاف",
        "Split multiple explicit duties",
    )

    missing = [
        fragment
        for fragment in required
        if fragment not in combined
    ]

    assert not missing
