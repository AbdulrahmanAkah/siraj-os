from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import socket

from src.application.project_runtime import initialize_project
from src.application.shamela_extraction_quality_audit import (
    PENDING_HUMAN_ANNOTATION,
    evaluate_gold_annotations,
    run_shamela_extraction_quality_audit,
)


BOOK_COUNTS = {
    400: 22,
    619: 17,
    5: 12,
    405: 12,
    151020: 12,
}


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


def _audit_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    project = tmp_path / "project"
    initialize_project(
        str(project),
        "quality-audit",
        "تدقيق جودة الاستخراج",
    )
    pilot = project / "working" / "shamela-pilot-corpus"
    extraction = (
        project / "working" / "shamela-historical-extraction-pilot"
    )
    output = (
        project / "working" / "shamela-extraction-quality-audit"
    )
    fake_shamela = tmp_path / "shamela4"
    fake_shamela.mkdir()
    marker = fake_shamela / "read-only-marker"
    marker.write_bytes(b"unchanged")

    entities: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    relations: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    temporals: list[dict[str, object]] = []
    isnads: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    queue: list[dict[str, object]] = []
    ledger: list[dict[str, object]] = []

    for book_id, segment_count in sorted(BOOK_COUNTS.items()):
        source_id = f"source-{book_id}"
        ledger.append(
            {
                "book_id": book_id,
                "source_id": source_id,
                "source_type": "SHAMELA_LOCAL_BOOK",
                "ingestion_status": "ACCEPTED",
            }
        )
        segments = []
        headings = []
        for segment_id in range(1, segment_count + 1):
            if segment_id % 7 == 1:
                text = (
                    "حدثنا أبو عبد الله عن محمد بن أحمد سنة 241 هـ."
                )
            elif segment_id % 7 == 2:
                text = (
                    "توفي الأمير خالد بن يزيد في بغداد سنة 200 هـ."
                )
            elif segment_id % 7 == 3:
                text = "غزا القائد المدينة ثم عاد إلى مصر."
            elif segment_id % 7 == 4:
                text = "هذا نص عام لا يقرر حدثاً تاريخياً."
            elif segment_id % 7 == 5:
                text = "قال أبو الحسن إن بغداد مدينة معروفة."
            elif segment_id % 7 == 6:
                text = "قبل المعركة انتقل محمد بن علي إلى الشام."
            else:
                text = "سطر أول\nسطر ثان\nسطر ثالث\nسطر رابع"
            locator = (
                "shamela://local/test-installation/"
                f"book/{book_id}/volume/1/page/{segment_id}"
                f"?database_sha256={'a' * 64}&segment_id={segment_id}"
            )
            segments.append(
                {
                    "segment_id": segment_id,
                    "number": segment_id,
                    "volume": None if segment_id == 1 else 1,
                    "page": segment_id,
                    "locator": locator,
                    "body_original": text,
                    "body_normalized": text,
                    "foot_original": "حاشية منفصلة",
                    "foot_normalized": "حاشية منفصلة",
                }
            )
            if segment_id == 1:
                headings.append(
                    {
                        "heading_id": 1,
                        "parent_heading_id": 0,
                        "page_segment_id": 1,
                        "locator": locator,
                        "text_original": "حدثنا أبو عبد الله",
                        "text_normalized": "حدثنا أبو عبد الله",
                    }
                )
            start = text.find("بغداد")
            if start >= 0:
                mention_id = f"mention-{book_id}-{segment_id}"
                span = {
                    "start": start,
                    "end": start + len("بغداد"),
                    "text": "بغداد",
                }
                entities.append(
                    {
                        "mention_id": mention_id,
                        "source_id": source_id,
                        "locator": locator,
                        "segment_id": segment_id,
                        "original_text_span": span,
                        "normalized_surface_form": "بغداد",
                        "entity_type_candidate": ["PLACE", "CITY"],
                        "extraction_confidence": 0.96,
                        "extractor_version": "test",
                        "mention_context": "BODY",
                        "rule_id": "ENTITY_PLACE_DICTIONARY_V1",
                    }
                )
            event_start = text.find("توفي")
            if event_start >= 0:
                event_id = f"event-{book_id}-{segment_id}"
                event_span = {
                    "start": event_start,
                    "end": len(text),
                    "text": text[event_start:],
                }
                events.append(
                    {
                        "event_mention_id": event_id,
                        "source_id": source_id,
                        "locator": locator,
                        "segment_id": segment_id,
                        "original_text_span": event_span,
                        "event_type": "DEATH_EVENT",
                        "participants": [],
                        "places": [],
                        "temporal_expression": "سنة 200 هـ",
                        "temporal_precision": "YEAR",
                        "extraction_confidence": 0.78,
                        "rule_id": "EVENT_DEATH_V1",
                    }
                )
                claims.append(
                    {
                        "claim_id": f"claim-{book_id}-{segment_id}",
                        "source_id": source_id,
                        "locator": locator,
                        "segment_id": segment_id,
                        "original_text": event_span["text"],
                        "original_text_span": event_span,
                        "normalized_claim": "وفاة منسوبة إلى المصدر",
                        "subject": "خالد بن يزيد",
                        "predicate": "DEATH_EVENT",
                        "object": "بغداد",
                        "claim_modality": "SOURCE_ASSERTION",
                        "historical_confidence": (
                            "SOURCE_ATTESTED_UNVERIFIED"
                        ),
                        "extraction_confidence": 0.78,
                        "review_status": "HUMAN_REVIEW_REQUIRED",
                        "evidence_id": f"evidence-{book_id}-{segment_id}",
                        "rule_id": "EVENT_DEATH_V1",
                    }
                )
            temporal_start = text.find("سنة")
            if temporal_start >= 0:
                temporal_text = text[
                    temporal_start:
                    text.find(".", temporal_start)
                ]
                temporals.append(
                    {
                        "temporal_id": (
                            f"temporal-{book_id}-{segment_id}"
                        ),
                        "source_id": source_id,
                        "locator": locator,
                        "segment_id": segment_id,
                        "original_text_span": {
                            "start": temporal_start,
                            "end": temporal_start + len(temporal_text),
                            "text": temporal_text,
                        },
                        "normalized_value": temporal_text,
                        "calendar": "HIJRI",
                        "temporal_type": "YEAR",
                        "temporal_precision": "YEAR",
                        "conversion_status": "NOT_CONVERTED",
                        "rule_id": "TEMPORAL_HIJRI_YEAR_V1",
                    }
                )
        _write_json(
            pilot / "books" / str(book_id) / "book.v1.json",
            {
                "schema_version": "shamela-pilot-book-v1",
                "adapter_version": "test",
                "source_id": source_id,
                "source_metadata": {
                    "book_id": book_id,
                    "title": f"كتاب {book_id}",
                },
                "segment_count": len(segments),
                "heading_count": len(headings),
                "segments": segments,
                "headings": headings,
            },
        )
    _write_json(
        pilot / "shamela-pilot-source-ledger.json",
        ledger,
    )

    candidate = {
        "candidate_id": "candidate-baghdad",
        "canonical_name": "بغداد",
        "entity_type": ["PLACE", "CITY"],
        "aliases": ["بغداد"],
        "linked_mentions": [entities[0]["mention_id"]],
        "merge_confidence": 0.45,
        "review_status": "HUMAN_REVIEW_REQUIRED",
        "rule_ids": ["ENTITY_PLACE_DICTIONARY_V1"],
    }
    candidates.append(candidate)
    queue.append(
        {
            "review_id": "review-baghdad",
            "candidate_id": candidate["candidate_id"],
            "review_status": "HUMAN_REVIEW_REQUIRED",
            "reason": "INSUFFICIENT_EXACT_HIGH_CONFIDENCE_SUPPORT",
            "mention_ids": candidate["linked_mentions"],
        }
    )
    extraction_files = {
        "extraction-run-manifest.json": {
            "schema_version": "test",
            "run_id": "test-extraction-run",
            "status": "VALID",
        },
        "entity-mentions.json": {"entity_mentions": entities},
        "canonical-entity-candidates.json": {
            "canonical_entity_candidates": candidates
        },
        "event-mentions.json": {"event_mentions": events},
        "historical-claims.json": {"historical_claims": claims},
        "relation-mentions.json": {"relation_mentions": relations},
        "isnad-chains.json": {"isnad_chains": isnads},
        "temporal-mentions.json": {"temporal_mentions": temporals},
        "entity-resolution-review-queue.json": {
            "review_items": queue
        },
    }
    for filename, payload in extraction_files.items():
        _write_json(extraction / filename, payload)
    return project, pilot, extraction, output, marker


def test_audit_sample_is_deterministic_and_provenance_complete(
    tmp_path: Path,
) -> None:
    project, pilot, extraction, output, _ = _audit_fixture(tmp_path)
    first = run_shamela_extraction_quality_audit(
        project,
        pilot,
        extraction,
        output,
    )
    first_manifest = (
        output / "audit-sample-manifest.json"
    ).read_bytes()
    second = run_shamela_extraction_quality_audit(
        project,
        pilot,
        extraction,
        output,
    )
    assert first["audit_id"] == second["audit_id"]
    assert first_manifest == (
        output / "audit-sample-manifest.json"
    ).read_bytes()
    assert {
        "audit-sample-manifest.json",
        "gold-annotation-template.json",
        "gold-annotation-review.md",
        "current-extraction-on-gold-sample.json",
        "human-review-reason-analysis.json",
        "extraction-error-taxonomy.json",
        "extraction-quality-baseline.json",
        "extraction-improvement-backlog.json",
        "knowledge-graph-readiness-gate.json",
        "extraction-quality-audit-report.md",
    } == {
        item.name
        for item in output.iterdir()
        if item.is_file()
    }

    manifest = json.loads(first_manifest)
    assert manifest["sample_count"] == 65
    counts: dict[int, int] = {}
    for segment in manifest["segments"]:
        counts[segment["book_id"]] = (
            counts.get(segment["book_id"], 0) + 1
        )
        assert segment["source_id"]
        assert segment["locator"].startswith("shamela://")
        assert segment["selection_reasons"]
    assert counts == {5: 10, 400: 20, 405: 10, 619: 15, 151020: 10}
    review = json.loads(
        (output / "human-review-reason-analysis.json").read_text(
            encoding="utf-8"
        )
    )
    assert review["classification_count_consistent"] is True
    assert sum(
        item["count"]
        for item in review["category_distribution"]
    ) == review["human_review_required_total"]
    assert {
        "PLACE_PERSON_AMBIGUITY",
        "NARRATOR_CONTEXT_AMBIGUITY",
        "COMMON_NOUN_MISTAKEN_FOR_PERSON",
    }.issubset(
        {
            item["category"]
            for item in review["category_distribution"]
        }
    )


def test_gold_text_is_original_and_pending_is_not_scored(
    tmp_path: Path,
) -> None:
    project, pilot, extraction, output, _ = _audit_fixture(tmp_path)
    run_shamela_extraction_quality_audit(
        project,
        pilot,
        extraction,
        output,
    )
    gold = json.loads(
        (output / "gold-annotation-template.json").read_text(
            encoding="utf-8"
        )
    )
    current = json.loads(
        (
            output / "current-extraction-on-gold-sample.json"
        ).read_text(encoding="utf-8")
    )
    books = {
        book_id: json.loads(
            (
                pilot
                / "books"
                / str(book_id)
                / "book.v1.json"
            ).read_text(encoding="utf-8")
        )
        for book_id in BOOK_COUNTS
    }
    for annotation in gold["annotations"]:
        source_book = books[annotation["book_id"]]
        original = next(
            item["body_original"]
            for item in source_book["segments"]
            if item["segment_id"] == annotation["segment_id"]
        )
        assert annotation["original_text"] == original
        assert annotation["reviewer_status"] == PENDING_HUMAN_ANNOTATION
        assert annotation["expected_entities"] == []
    evaluation = evaluate_gold_annotations(gold, current)
    assert evaluation["status"] == PENDING_HUMAN_ANNOTATION
    assert evaluation["evaluated_segments"] == 0
    assert all(
        value is None
        for value in evaluation["metrics"].values()
    )


def test_exact_and_partial_scores_remain_separate() -> None:
    gold = {
        "annotations": [
            {
                "source_id": "source",
                "segment_id": 1,
                "reviewer_status": "REVIEWED",
                "expected_entities": [
                    {
                        "span": {"start": 0, "end": 5, "text": "محمد"},
                        "normalized_surface_form": "محمد",
                        "entity_types": ["PERSON"],
                    }
                ],
                "expected_events": [],
                "expected_relations": [],
                "expected_temporal_mentions": [],
                "expected_isnad": [],
            }
        ]
    }
    current = {
        "segments": [
            {
                "source_id": "source",
                "segment_id": 1,
                "entities": [
                    {
                        "original_text_span": {
                            "start": 0,
                            "end": 4,
                            "text": "محمد",
                        },
                        "normalized_surface_form": "محمد",
                        "entity_type_candidate": ["PERSON"],
                    }
                ],
                "events": [],
                "relations": [],
                "temporal_mentions": [],
                "isnad_chains": [],
            }
        ]
    }
    result = evaluate_gold_annotations(gold, current)
    assert result["metrics"]["entity"]["exact"]["true_positive"] == 0
    assert (
        result["metrics"]["entity"]["partial_overlap"]["true_positive"]
        == 1
    )
    assert result["metrics"]["span_exact_match"] == 0.0
    assert result["metrics"]["span_overlap_match"] == 1.0


def test_expected_labels_do_not_mutate_current_extraction() -> None:
    current = {
        "segments": [
            {
                "source_id": "source",
                "segment_id": 1,
                "entities": [],
                "events": [],
                "relations": [],
                "temporal_mentions": [],
                "isnad_chains": [],
            }
        ]
    }
    original = deepcopy(current)
    gold = {
        "annotations": [
            {
                "source_id": "source",
                "segment_id": 1,
                "reviewer_status": "REVIEWED",
                "expected_entities": [
                    {
                        "span": {"start": 0, "end": 4, "text": "محمد"},
                        "normalized_surface_form": "محمد",
                        "entity_types": ["PERSON"],
                    }
                ],
                "expected_events": [],
                "expected_relations": [],
                "expected_temporal_mentions": [],
                "expected_isnad": [],
            }
        ]
    }
    evaluate_gold_annotations(gold, current)
    assert current == original


def test_evaluator_never_matches_across_segments() -> None:
    gold = {
        "annotations": [
            {
                "source_id": "source",
                "segment_id": 1,
                "reviewer_status": "REVIEWED",
                "expected_entities": [
                    {
                        "span": {"start": 0, "end": 4, "text": "محمد"},
                        "normalized_surface_form": "محمد",
                        "entity_types": ["PERSON"],
                    }
                ],
                "expected_events": [],
                "expected_relations": [],
                "expected_temporal_mentions": [],
                "expected_isnad": [],
            }
        ]
    }
    current = {
        "segments": [
            {
                "source_id": "source",
                "segment_id": 2,
                "entities": [
                    {
                        "original_text_span": {
                            "start": 0,
                            "end": 4,
                            "text": "محمد",
                        },
                        "normalized_surface_form": "محمد",
                        "entity_type_candidate": ["PERSON"],
                    }
                ],
                "events": [],
                "relations": [],
                "temporal_mentions": [],
                "isnad_chains": [],
            }
        ]
    }
    result = evaluate_gold_annotations(gold, current)
    assert result["metrics"]["entity"]["exact"]["true_positive"] == 0
    assert result["metrics"]["entity"]["exact"]["false_negative"] == 1


def test_audit_is_offline_and_never_touches_shamela(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project, pilot, extraction, output, marker = _audit_fixture(tmp_path)
    before = (marker.read_bytes(), marker.stat().st_mtime_ns)

    def deny_network(*_args, **_kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    run_shamela_extraction_quality_audit(
        project,
        pilot,
        extraction,
        output,
    )
    assert (marker.read_bytes(), marker.stat().st_mtime_ns) == before
