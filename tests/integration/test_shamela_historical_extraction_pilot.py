from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import socket

import pytest

from src.application.cli_v2 import build_parser
from src.application.project_ingestion_runtime import ingest_project
from src.application.project_runtime import (
    add_source,
    initialize_project,
)
from src.application.shamela_historical_extraction import (
    run_shamela_historical_extraction,
)


BOOK_TEXTS = {
    5: (
        "حدثنا أبو عبد الله قال أخبرنا محمد بن أحمد عن أبي يوسف. "
        "توفي الإمام أحمد بن حنبل سنة 241 هـ في بغداد."
    ),
    400: (
        "الخليفة المنصور أسس بغداد سنة 145 هـ. "
        "ثم حكم الخليفة المهدي في العراق."
    ),
    405: (
        "قيل إن الأمير محمد بن يوسف ولد في مصر نحو سنة 190 هـ. "
        "ورحل أبو الحسن إلى بغداد بعد فتح المدينة."
    ),
    619: (
        "ذكر المؤرخ عبد الرحمن أن الملك صالح حكم مصر سنة 650 هـ. "
        "وفي رواية أخرى قيل إن الملك صالح لم يحكم مصر سنة 650 هـ."
    ),
    151020: (
        "صنف الإمام جلال الدين السيوطي كتاب صون المنطق. "
        "وعارضت فرقة المعتزلة طائفة أخرى في بغداد."
    ),
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


def _fixture_pilot(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path]:
    project = tmp_path / "project"
    initialize_project(
        str(project),
        "historical-pilot",
        "استخراج تاريخي تجريبي",
    )
    pilot = project / "working" / "shamela-pilot-corpus"
    fake_installation = tmp_path / "shamela4"
    fake_installation.mkdir()
    (fake_installation / "read-only-marker").write_bytes(b"unchanged")
    catalog = []
    ledger = []
    source_ids: set[str] = set()

    for book_id, body in sorted(BOOK_TEXTS.items()):
        locator = (
            "shamela://local/fixture-installation/"
            f"book/{book_id}/volume/1/page/1"
            f"?database_sha256={'a' * 64}&segment_id=1"
        )
        book_root = pilot / "books" / str(book_id)
        body_path = book_root / "body.txt"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text(
            f"[Shamela locator: {locator}]\n{body}\n",
            encoding="utf-8",
            newline="\n",
        )
        book_payload = {
            "schema_version": "shamela-pilot-book-v1",
            "adapter_version": "shamela-local-adapter-v1",
            "source_metadata": {
                "book_id": book_id,
                "title": f"كتاب {book_id}",
                "author": "مؤلف تجريبي",
                "category": "تاريخ",
            },
            "segment_count": 1,
            "heading_count": 0,
            "segments": [
                {
                    "segment_id": 1,
                    "volume": "1",
                    "page": 1,
                    "locator": locator,
                    "body_original": body,
                    "body_normalized": body,
                    "foot_original": (
                        "سر الحاشية الذي يجب ألا يدخل المتن"
                    ),
                    "foot_normalized": (
                        "سر الحاشية الذي يجب ألا يدخل المتن"
                    ),
                }
            ],
            "headings": [],
        }
        _write_json(book_root / "book.v1.json", book_payload)
        registration = add_source(
            str(project),
            str(body_path),
            title=f"كتاب {book_id}",
            language="ar",
            classification="INTERNAL",
            source_type="SHAMELA_LOCAL_BOOK",
            rights_status="RIGHTS_UNVERIFIED",
            source_locator=locator,
            provenance={
                "book_id": book_id,
                "adapter_version": "shamela-local-adapter-v1",
            },
        )
        source_id = registration["source"]["source_id"]
        source_ids.add(source_id)
        catalog.append(
            {
                "book_id": book_id,
                "title": f"كتاب {book_id}",
                "book_artifact": (
                    f"books/{book_id}/book.v1.json"
                ),
                "body_artifact": f"books/{book_id}/body.txt",
            }
        )
        ledger.append(
            {
                "book_id": book_id,
                "source_id": source_id,
                "source_type": "SHAMELA_LOCAL_BOOK",
                "source_locator": locator,
                "content_hash": sha256(
                    body_path.read_bytes()
                ).hexdigest(),
                "rights_status": "RIGHTS_UNVERIFIED",
                "ingestion_status": "ACCEPTED",
            }
        )

    _write_json(pilot / "shamela-pilot-catalog.json", catalog)
    _write_json(
        pilot / "shamela-pilot-source-ledger.json",
        ledger,
    )
    ingestion = ingest_project(
        str(project),
        source_ids=source_ids,
        working_name="shamela-pilot-ingestion",
    )
    assert ingestion["accepted_count"] == 5
    output = (
        project
        / "working"
        / "shamela-historical-extraction-pilot"
    )
    return project, pilot, output, fake_installation


def _load(output: Path, filename: str, key: str) -> list[dict]:
    payload = json.loads(
        (output / filename).read_text(encoding="utf-8")
    )
    return payload[key]


def test_extraction_provenance_spans_and_body_foot_separation(
    tmp_path: Path,
) -> None:
    project, pilot, output, _ = _fixture_pilot(tmp_path)
    result = run_shamela_historical_extraction(
        project,
        pilot,
        output,
    )
    claims = _load(
        output,
        "historical-claims.json",
        "historical_claims",
    )
    events = _load(
        output,
        "event-mentions.json",
        "event_mentions",
    )
    mentions = _load(
        output,
        "entity-mentions.json",
        "entity_mentions",
    )

    assert result["status"] == "VALID"
    assert len(result["coverage"]) == 5
    assert claims and events and mentions
    assert all(
        item["source_id"]
        and item["locator"]
        and item["original_text"]
        and item["evidence_id"]
        for item in claims
    )
    assert all(
        item["original_text_span"]["text"]
        for item in events
    )
    assert all(
        "سر الحاشية" not in item["original_text"]
        for item in claims
    )
    validation = json.loads(
        (
            output / "extraction-validation-report.json"
        ).read_text(encoding="utf-8")
    )
    assert validation["status"] == "VALID"


def test_isnad_resolution_and_temporal_precision_are_conservative(
    tmp_path: Path,
) -> None:
    project, pilot, output, _ = _fixture_pilot(tmp_path)
    run_shamela_historical_extraction(
        project,
        pilot,
        output,
    )
    chains = _load(
        output,
        "isnad-chains.json",
        "isnad_chains",
    )
    mentions = _load(
        output,
        "entity-mentions.json",
        "entity_mentions",
    )
    candidates = _load(
        output,
        "canonical-entity-candidates.json",
        "canonical_entity_candidates",
    )
    temporals = _load(
        output,
        "temporal-mentions.json",
        "temporal_mentions",
    )

    assert chains
    assert all(
        chain["validation_status"]
        == "UNASSESSED_TRANSMISSION"
        for chain in chains
    )
    narrator_ids = {
        item["mention_id"]
        for item in mentions
        if item["mention_context"] == "ISNAD"
    }
    assert narrator_ids
    assert not any(
        item["review_status"] == "AUTO_LINK_SAFE"
        and narrator_ids.intersection(item["linked_mentions"])
        for item in candidates
    )
    approximate = [
        item
        for item in temporals
        if item["temporal_precision"] == "APPROXIMATE"
    ]
    assert approximate
    assert all(
        item["conversion_status"] == "NOT_CONVERTED"
        for item in approximate
    )


def test_conflicting_reports_remain_separate_and_outputs_are_deterministic(
    tmp_path: Path,
) -> None:
    project, pilot, output, _ = _fixture_pilot(tmp_path)
    first = run_shamela_historical_extraction(
        project,
        pilot,
        output,
    )
    names = (
        "entity-mentions.json",
        "canonical-entity-candidates.json",
        "event-mentions.json",
        "historical-claims.json",
        "relation-mentions.json",
        "isnad-chains.json",
        "temporal-mentions.json",
        "entity-resolution-review-queue.json",
        "extraction-coverage-report.json",
        "extraction-validation-report.json",
        "extraction-run-manifest.json",
    )
    first_hashes = {
        name: sha256((output / name).read_bytes()).hexdigest()
        for name in names
    }
    second = run_shamela_historical_extraction(
        project,
        pilot,
        output,
    )
    second_hashes = {
        name: sha256((output / name).read_bytes()).hexdigest()
        for name in names
    }
    claims = _load(
        output,
        "historical-claims.json",
        "historical_claims",
    )

    assert first["run_id"] == second["run_id"]
    assert first_hashes == second_hashes
    disputed = [
        item
        for item in claims
        if "الملك صالح" in item["original_text"]
    ]
    assert len({item["claim_id"] for item in disputed}) >= 2
    assert all(
        item["review_status"] == "HUMAN_REVIEW_REQUIRED"
        for item in disputed
    )


def test_runtime_is_offline_and_does_not_touch_shamela(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, pilot, output, shamela = _fixture_pilot(tmp_path)
    before = {
        path.name: (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            sha256(path.read_bytes()).hexdigest(),
        )
        for path in shamela.iterdir()
        if path.is_file()
    }

    def deny_network(*args, **kwargs):
        raise AssertionError("NETWORK_ACCESS_FORBIDDEN")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    run_shamela_historical_extraction(
        project,
        pilot,
        output,
    )
    after = {
        path.name: (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            sha256(path.read_bytes()).hexdigest(),
        )
        for path in shamela.iterdir()
        if path.is_file()
    }
    assert before == after


def test_cli_exposes_bounded_extraction_only() -> None:
    args = build_parser().parse_args(
        [
            "shamela",
            "extract-pilot",
            "--project-root",
            "C:/project",
            "--pilot-root",
            "C:/project/working/shamela-pilot-corpus",
            "--output-root",
            (
                "C:/project/working/"
                "shamela-historical-extraction-pilot"
            ),
        ]
    )
    assert args.command == "shamela"
    assert args.action == "extract-pilot"
    assert args.segment_limit_per_book is None
