from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

from src.application.cli_v2 import main
from src.application.project_runtime import initialize_project
from src.application.shamela_extraction_quality_audit import (
    COMPLETED,
    NEEDS_REVIEW,
    GoldAnnotationStore,
    GoldAnnotationValidationError,
    build_local_workbench_server,
)
from src.application.shamela_extraction_quality_audit.runtime import (
    AUDIT_SCHEMA_VERSION,
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


def _annotation(number: int, status: str = "PENDING_HUMAN_ANNOTATION") -> dict:
    text = f"محمد في بغداد سنة 20{number} هـ"
    span = {"start": 0, "end": 4, "text": "محمد"}
    current = {
        "audit_segment_id": f"audit-{number}",
        "source_id": "source-1",
        "segment_id": number,
        "locator": f"shamela://local/test/book/1?segment_id={number}",
        "entities": [
            {
                "mention_id": f"mention-{number}",
                "original_text_span": span,
                "normalized_surface_form": "محمد",
                "entity_type_candidate": ["PERSON"],
            }
        ],
        "events": [],
        "relations": [],
        "claims": [],
        "temporal_mentions": [],
        "isnad_chains": [],
    }
    return {
        "annotation_id": f"annotation-{number}",
        "audit_segment_id": f"audit-{number}",
        "book_id": 1,
        "book_title": "كتاب تجريبي",
        "source_id": "source-1",
        "segment_id": number,
        "locator": current["locator"],
        "original_text": text,
        "expected_entities": [],
        "expected_entity_types": [],
        "expected_events": [],
        "expected_relations": [],
        "expected_temporal_mentions": [],
        "expected_isnad": [],
        "explicitly_absent_items": [],
        "reviewer_status": status,
        "reviewer_notes": "",
        "current_extraction": current,
    }


def _workbench_fixture(tmp_path: Path) -> tuple[Path, GoldAnnotationStore]:
    project = tmp_path / "project"
    initialize_project(str(project), "gold-workbench", "مراجعة ذهبية")
    root = project / "working" / "shamela-extraction-quality-audit"
    annotations = [_annotation(1), _annotation(2)]
    current = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "segments": [item["current_extraction"] for item in annotations],
    }
    _write_json(
        root / "gold-annotation-template.json",
        {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "annotation_status": "PENDING_HUMAN_ANNOTATION",
            "annotations": annotations,
        },
    )
    _write_json(root / "current-extraction-on-gold-sample.json", current)
    _write_json(
        root / "extraction-quality-baseline.json",
        {"structural_integrity": {"span_integrity_rate": 1.0}},
    )
    gates = [
        ("ENTITY_PRECISION", ">=", 0.0),
        ("ENTITY_RECALL", ">=", 0.0),
        ("EVENT_PRECISION", ">=", 0.0),
        ("EVENT_RECALL", ">=", 0.0),
        ("RELATION_PRECISION", ">=", 0.0),
        ("TEMPORAL_PRECISION", ">=", 0.0),
        ("ISNAD_DETECTION_PRECISION", ">=", 0.0),
        ("LOCATOR_INTEGRITY", "==", 1.0),
        ("SPAN_EXACT_INTEGRITY", ">=", 0.0),
        ("UNSUPPORTED_MERGE_RATE", "==", 0.0),
        ("FALSE_POSITIVE_RATE", "<=", 1.0),
        ("DETERMINISTIC_REPRODUCIBILITY", "==", 1.0),
    ]
    _write_json(
        root / "knowledge-graph-readiness-gate.json",
        {
            "thresholds": [
                {"gate_id": gate, "operator": operator, "threshold": value}
                for gate, operator, value in gates
            ]
        },
    )
    return project, GoldAnnotationStore(root)


def test_accept_current_creates_versioned_backup_and_preserves_identity(
    tmp_path: Path,
) -> None:
    _, store = _workbench_fixture(tmp_path)
    initial = store.load()["annotations"][0]
    result = store.accept_current("annotation-1")
    updated = store.load()["annotations"][0]
    assert result["backup_file"] == "gold-annotation-template.backup-000001.json"
    assert (store.backup_root / result["backup_file"]).is_file()
    assert updated["reviewer_status"] == COMPLETED
    assert updated["expected_entities"][0]["normalized_surface_form"] == "محمد"
    for key in ("original_text", "source_id", "locator", "segment_id"):
        assert updated[key] == initial[key]


def test_store_rejects_immutable_updates_and_invalid_spans(
    tmp_path: Path,
) -> None:
    _, store = _workbench_fixture(tmp_path)
    with pytest.raises(GoldAnnotationValidationError, match="IMMUTABLE"):
        store.update("annotation-1", {"original_text": "معدل"})
    with pytest.raises(GoldAnnotationValidationError, match="SPAN_OUT_OF_RANGE"):
        store.update(
            "annotation-1",
            {
                "expected_entities": [
                    {
                        "span": {"start": 0, "end": 999, "text": "محمد"},
                        "normalized_surface_form": "محمد",
                        "entity_types": ["PERSON"],
                    }
                ]
            },
        )
    assert store.load()["annotations"][0]["expected_entities"] == []


def test_progress_tracks_statuses_and_completed_annotation_types(
    tmp_path: Path,
) -> None:
    _, store = _workbench_fixture(tmp_path)
    store.accept_current("annotation-1")
    store.update(
        "annotation-2",
        {
            "reviewer_status": NEEDS_REVIEW,
            "reviewer_notes": "الاسم يحتاج تحققاً",
        },
    )
    progress = store.progress()
    assert progress["total"] == 2
    assert progress["completed"] == 1
    assert progress["needs_review"] == 1
    assert progress["pending"] == 0
    assert progress["completed_annotation_counts"]["entities"] == 1
    assert progress["by_book"]["1"]["completion_percentage"] == 50.0


def test_evaluation_is_blocked_until_every_annotation_completed(
    tmp_path: Path,
) -> None:
    _, store = _workbench_fixture(tmp_path)
    store.accept_current("annotation-1")
    with pytest.raises(
        GoldAnnotationValidationError,
        match="EVALUATION_REQUIRES_ALL_COMPLETED",
    ):
        store.evaluate()
    store.accept_current("annotation-2")
    result = store.evaluate()
    assert result["semantic_baseline"] == "semantic-baseline.json"
    assert (store.audit_root / "semantic-baseline.json").is_file()
    assert (store.audit_root / "semantic-baseline.md").is_file()
    assert (store.audit_root / "knowledge-graph-readiness-evaluation.json").is_file()


def test_workbench_server_is_localhost_only(tmp_path: Path) -> None:
    _, store = _workbench_fixture(tmp_path)
    with pytest.raises(GoldAnnotationValidationError, match="LOCALHOST_ONLY"):
        build_local_workbench_server(store.audit_root, host="0.0.0.0")
    server = build_local_workbench_server(store.audit_root, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[1] > 0
    finally:
        server.server_close()


def test_localhost_api_and_cli_review_commands(tmp_path: Path) -> None:
    project, store = _workbench_fixture(tmp_path)
    server = build_local_workbench_server(store.audit_root, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/state",
            timeout=3,
        ) as response:
            state = json.loads(response.read().decode("utf-8"))
        assert state["progress"]["pending"] == 2
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
    assert main(
        [
            "--json",
            "shamela",
            "audit-review",
            "status",
            "--project-root",
            str(project),
        ]
    ) == 0
    assert main(
        [
            "--json",
            "shamela",
            "audit-review",
            "evaluate",
            "--project-root",
            str(project),
        ]
    ) == 8
