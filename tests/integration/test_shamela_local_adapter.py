from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from src.application.project_runtime import initialize_project, list_sources
from src.application.cli_v2 import build_parser
from src.application.shamela_local_adapter import ShamelaLocalSourceAdapter, build_pilot_corpus
from src.application.shamela_local_adapter.lucene_read_only import (
    LuceneStoredDocument,
    LuceneUnavailableError,
)


def _create_database(path: Path, statements: list[tuple[str, tuple[object, ...] | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for statement, parameters in statements:
            connection.execute(statement, parameters or ())
        connection.commit()
    finally:
        connection.close()


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns, sha256(path.read_bytes()).hexdigest())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class FakeLuceneBridge:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable

    def read_book(self, index_path: str | Path, book_id: int, maximum_documents: int) -> list[LuceneStoredDocument]:
        if self.unavailable:
            raise LuceneUnavailableError("LUCENE_RUNTIME_UNAVAILABLE")
        index_name = Path(index_path).name
        if index_name == "title":
            return [LuceneStoredDocument(f"{book_id}-1", f"عنوان {book_id}", None)]
        return [
            LuceneStoredDocument(f"{book_id}-1", f"نص أصلي للكتاب {book_id}\u200b", f"حاشية {book_id}"),
            LuceneStoredDocument(f"{book_id}-2", f"فقرة ثانية للكتاب {book_id}", ""),
        ][:maximum_documents]


def _fixture_installation(tmp_path: Path) -> tuple[Path, Path]:
    installation = tmp_path / "shamela4"
    database = installation / "database"
    _create_database(
        database / "master.db",
        [
            ("CREATE TABLE book(book_id INTEGER PRIMARY KEY,book_name TEXT,book_category INTEGER,main_author INTEGER,meta_data TEXT)", None),
            ("CREATE TABLE author(author_id INTEGER PRIMARY KEY,author_name TEXT)", None),
            ("CREATE TABLE category(category_id INTEGER PRIMARY KEY,category_name TEXT)", None),
        ],
    )
    selections = (
        (619, "القوافي الندية في السيرة المحمدية", "السيرة النبوية"),
        (400, "الحوادث الجامعة والتجارب النافعة", "التاريخ"),
        (5, "أسماء المدلسين", "التراجم والطبقات"),
        (151020, "جهد القريحة في تجريد النصيحة", "الفرق والردود"),
        (405, "فضائل مصر المحروسة", "البلدان والرحلات"),
    )
    connection = sqlite3.connect(database / "master.db")
    try:
        for category_id, (book_id, title, category) in enumerate(selections, start=1):
            connection.execute("INSERT INTO author VALUES(?,?)", (category_id, f"مؤلف {book_id}"))
            connection.execute("INSERT INTO category VALUES(?,?)", (category_id, category))
            connection.execute("INSERT INTO book VALUES(?,?,?,?,?)", (book_id, title, category_id, category_id, json.dumps({"fixture": True})))
        connection.commit()
    finally:
        connection.close()
    for book_id, _title, _category in selections:
        suffix = f"{book_id % 1000:03d}"
        _create_database(
            database / "book" / suffix / f"{book_id}.db",
            [
                ("CREATE TABLE page(id INTEGER PRIMARY KEY,part TEXT,page INTEGER,number INTEGER,services TEXT)", None),
                ("CREATE TABLE title(id INTEGER PRIMARY KEY,page INTEGER,parent INTEGER)", None),
                ("INSERT INTO page VALUES(1,'1',1,1,NULL)", None),
                ("INSERT INTO page VALUES(2,'1',2,2,NULL)", None),
                ("INSERT INTO title VALUES(1,1,0)", None),
            ],
        )
    for name in ("page", "title"):
        index = database / "store" / name
        index.mkdir(parents=True)
        (index / "segments_1").write_bytes(b"fixture-read-only-index")
    discovery = tmp_path / "discovery"
    discovery.mkdir()
    (discovery / "shamela-discovery-report.json").write_text(
        json.dumps({"installation": str(installation.resolve()), "storage_type": "HYBRID_SQLITE_AND_LUCENE"}), encoding="utf-8"
    )
    (discovery / "shamela-locator-proposal.json").write_text(
        json.dumps({"installation_fingerprint": "fixture-installation-fingerprint"}), encoding="utf-8"
    )
    return installation, discovery


def test_pilot_is_read_only_deterministic_and_preserves_segments(tmp_path: Path) -> None:
    installation, discovery = _fixture_installation(tmp_path)
    before = _snapshot(installation)
    adapter = ShamelaLocalSourceAdapter(installation, discovery, lucene_bridge=FakeLuceneBridge())
    first = build_pilot_corpus(adapter, tmp_path / "pilot-a")
    second = build_pilot_corpus(adapter, tmp_path / "pilot-b")

    assert _snapshot(installation) == before
    assert first["status"] == "VALID"
    assert len(first["catalog"]) == 5
    assert [item["book_id"] for item in first["catalog"]] == [5, 400, 405, 619, 151020]
    assert first["catalog"] == second["catalog"]
    for entry in first["catalog"]:
        staged = json.loads((tmp_path / "pilot-a" / entry["book_artifact"]).read_text(encoding="utf-8"))
        assert staged["segments"]
        assert all(segment["locator"].startswith("shamela://local/fixture-installation-fingerprint/") for segment in staged["segments"])
        assert all(segment["body_original"] != segment["body_normalized"] for segment in staged["segments"][:1])
        assert all("foot_original" in segment and "foot_normalized" in segment for segment in staged["segments"])
        assert "حاشية" not in (tmp_path / "pilot-a" / entry["body_artifact"]).read_text(encoding="utf-8")


def test_filter_inspection_and_project_ingestion_use_existing_pipeline(tmp_path: Path) -> None:
    installation, discovery = _fixture_installation(tmp_path)
    adapter = ShamelaLocalSourceAdapter(installation, discovery, lucene_bridge=FakeLuceneBridge())
    filtered = adapter.list_books(category="التاريخ")
    assert [item["book_id"] for item in filtered] == [400]
    assert adapter.inspect_book(619)["page_count"] == 2

    project = tmp_path / "project"
    initialize_project(str(project), "shamela-pilot", "اختبار الشاملة")
    result = build_pilot_corpus(adapter, tmp_path / "pilot", project_root=project)
    sources = list_sources(str(project))["sources"]
    assert result["ingestion"]["accepted_count"] == 5
    assert len(sources) == 5
    assert all(source["source_type"] == "SHAMELA_LOCAL_BOOK" for source in sources)
    assert all(source["source_locator"].startswith("shamela://local/") for source in sources)
    assert all(source["provenance"]["adapter_version"] == "shamela-local-adapter-v1" for source in sources)
    assert {item["ingestion_status"] for item in result["ledger"]} == {"ACCEPTED"}


def test_missing_sqlite_or_lucene_fails_without_source_mutation(tmp_path: Path) -> None:
    installation, discovery = _fixture_installation(tmp_path)
    before = _snapshot(installation)
    adapter = ShamelaLocalSourceAdapter(installation, discovery, lucene_bridge=FakeLuceneBridge(unavailable=True))
    with pytest.raises(LuceneUnavailableError):
        adapter.read_book(619)
    (installation / "database" / "master.db").unlink()
    with pytest.raises(FileNotFoundError):
        ShamelaLocalSourceAdapter(installation, discovery, lucene_bridge=FakeLuceneBridge())
    assert all(".tmp" not in name for name in _snapshot(installation))
    assert before.keys() - {"database/master.db"} == _snapshot(installation).keys()


def test_shamela_cli_exposes_only_bounded_commands() -> None:
    parser = build_parser()
    status = parser.parse_args(
        ["shamela", "status", "--installation-root", "C:/shamela4", "--discovery-root", "C:/reports"]
    )
    pilot = parser.parse_args(
        [
            "shamela", "import-pilot", "--installation-root", "C:/shamela4",
            "--discovery-root", "C:/reports", "--staging-root", "C:/staging", "--project-root", "C:/project",
        ]
    )
    assert (status.command, status.action) == ("shamela", "status")
    assert (pilot.command, pilot.action) == ("shamela", "import-pilot")
    with pytest.raises(SystemExit):
        parser.parse_args(["shamela", "import-all"])
