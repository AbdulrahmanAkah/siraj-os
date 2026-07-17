from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from src.application.shamela_local_discovery import (
    DiscoverySafetyError,
    classify_storage,
    discover_candidates,
    generate_discovery_reports,
    sanitize_public_path,
)


REPORT_FILES = {
    "shamela-installation-candidates.json",
    "shamela-storage-inventory.json",
    "shamela-schema-report.json",
    "shamela-sample-book-report.json",
    "shamela-locator-proposal.json",
    "shamela-integration-recommendation.md",
    "shamela-discovery-report.json",
}


def _create_database(path: Path, statements: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def _fixture_installation(tmp_path: Path) -> tuple[Path, int]:
    root = tmp_path / "shamela4"
    database = root / "database"
    book_id = 151020
    _create_database(
        database / "master.db",
        [
            "CREATE TABLE book(book_id INTEGER PRIMARY KEY,book_name TEXT,book_category INTEGER,main_author INTEGER,meta_data TEXT)",
            "CREATE TABLE author(author_id INTEGER PRIMARY KEY,author_name TEXT)",
            "CREATE TABLE category(category_id INTEGER PRIMARY KEY,category_name TEXT)",
            "INSERT INTO author VALUES(1,'الجلال السيوطي')",
            "INSERT INTO category VALUES(2,'الفرق والردود')",
            "INSERT INTO book VALUES(151020,'جهد القريحة في تجريد النصيحة',2,1,'{\"date\":\"test\"}')",
        ],
    )
    _create_database(
        database / "book" / "020" / "151020.db",
        [
            "CREATE TABLE page(id INTEGER PRIMARY KEY,part TEXT,page INTEGER,number INTEGER,services TEXT)",
            "CREATE TABLE title(id INTEGER PRIMARY KEY,page INTEGER,parent INTEGER)",
            "INSERT INTO page VALUES(1,'1',3,NULL,NULL)",
            "INSERT INTO page VALUES(2,'1',4,NULL,NULL)",
            "INSERT INTO title VALUES(1,1,0)",
        ],
    )
    _create_database(database / "service" / "S1.db", ["CREATE TABLE b(i INTEGER PRIMARY KEY,s BLOB)"])
    _create_database(database / "service" / "S2.db", ["CREATE TABLE roots(token BLOB,root BLOB)"])
    _create_database(database / "cover.db", ["CREATE TABLE cover(id INTEGER PRIMARY KEY,cover BLOB)"])
    for index_name, fields in {
        "page": b"book_key body foot page id",
        "title": b"book_key body parent page id",
    }.items():
        index = database / "store" / index_name
        index.mkdir(parents=True)
        (index / "_test.fnm").write_bytes(fields)
        (index / "segments_1").write_bytes(b"test-segment")
    (root / "shamela.exe").write_bytes(b"MZ-test")
    return root, book_id


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns, sha256(path.read_bytes()).hexdigest())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _load_reports(output: Path) -> dict[str, object]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(output.glob("*.json"))
    }


def test_discovery_is_read_only_bounded_and_deterministic(tmp_path: Path) -> None:
    installation, book_id = _fixture_installation(tmp_path)
    before = _snapshot(installation)
    full_text = "الحمد لله رب العالمين " * 100

    first = generate_discovery_reports(
        installation_root=installation,
        output_root=tmp_path / "report-a",
        candidate_paths=[installation],
        sample_book_id=book_id,
        page_excerpt=full_text,
        title_excerpt="مقدمة الطبعة الثانية",
    )
    second = generate_discovery_reports(
        installation_root=installation,
        output_root=tmp_path / "report-b",
        candidate_paths=[installation],
        sample_book_id=book_id,
        page_excerpt=full_text,
        title_excerpt="مقدمة الطبعة الثانية",
    )

    assert _snapshot(installation) == before
    assert set(first["files"]) == REPORT_FILES
    assert first["source_snapshot_unchanged"] is True
    assert _load_reports(tmp_path / "report-a") == _load_reports(tmp_path / "report-b")
    sample = json.loads((tmp_path / "report-a" / "shamela-sample-book-report.json").read_text(encoding="utf-8"))
    assert len(sample["verification_excerpt"]) <= 180
    assert full_text not in (tmp_path / "report-a" / "shamela-sample-book-report.json").read_text(encoding="utf-8")
    assert sample["text_extractable"] is True
    assert sample["volume_and_page_preserved"] is True


def test_output_inside_shamela_is_rejected_before_writing(tmp_path: Path) -> None:
    installation, book_id = _fixture_installation(tmp_path)
    with pytest.raises(DiscoverySafetyError):
        generate_discovery_reports(
            installation_root=installation,
            output_root=installation / "reports",
            candidate_paths=[installation],
            sample_book_id=book_id,
            page_excerpt="نص قصير",
            title_excerpt="عنوان",
        )
    assert not (installation / "reports").exists()


def test_storage_classification_uses_magic_not_only_extension(tmp_path: Path) -> None:
    disguised = tmp_path / "not-really-a-database.bin"
    disguised.write_bytes(b"SQLite format 3\x00" + bytes(64))
    assert classify_storage(disguised)["kind"] == "SQLITE"


def test_public_path_redaction_and_graceful_missing_discovery(tmp_path: Path) -> None:
    profile = tmp_path / "Users" / "operator"
    secret_path = profile / "AppData" / "Roaming" / "shamela_4"
    assert sanitize_public_path(secret_path, profile).startswith("%USERPROFILE%")
    assert discover_candidates([tmp_path / "missing-root"]) == []


def test_candidate_discovery_order_is_stable(tmp_path: Path) -> None:
    first = tmp_path / "B" / "Shamela"
    second = tmp_path / "A" / "الشاملة"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    normal = discover_candidates([tmp_path], max_depth=4)
    repeated = discover_candidates([tmp_path], max_depth=4)
    assert normal == repeated
    assert [item["path"].casefold() for item in normal] == sorted(item["path"].casefold() for item in normal)
