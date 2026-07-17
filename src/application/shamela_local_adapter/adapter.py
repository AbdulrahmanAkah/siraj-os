from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unicodedata
from typing import Any, Iterator

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id, integrity_hash

from .lucene_read_only import LuceneReadOnlyBridge, LuceneUnavailableError


ADAPTER_VERSION = "shamela-local-adapter-v1"
STAGING_SCHEMA_VERSION = "shamela-pilot-book-v1"
SOURCE_TYPE = "SHAMELA_LOCAL_BOOK"
RIGHTS_STATUS = "RIGHTS_UNVERIFIED"
_HARMFUL_INVISIBLES = {"\ufeff", "\u200b", "\u200c", "\u200d", "\u2060"}


def conservative_normalize(text: str) -> str:
    """Normalize Unicode and harmful invisibles without rewriting Arabic text."""

    normalized = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return "".join(character for character in normalized if character not in _HARMFUL_INVISIBLES)


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix=".siraj-", suffix=".tmp", delete=False)
        temporary_name = handle.name
        with handle:
            handle.write(payload)
            handle.flush()
        Path(temporary_name).replace(path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


class ShamelaLocalSourceAdapter:
    """A bounded SQLite/Lucene reader with no source-side write operations."""

    def __init__(
        self,
        installation_root: str | Path,
        discovery_root: str | Path,
        *,
        lucene_bridge: LuceneReadOnlyBridge | None = None,
        maximum_pages_per_book: int = 1_000,
    ) -> None:
        self.installation_root = Path(installation_root).resolve()
        self.discovery_root = Path(discovery_root).resolve()
        self.maximum_pages_per_book = maximum_pages_per_book
        self.discovery = self._read_discovery()
        self.locator_proposal = self._read_locator_proposal()
        self.database_root = self.installation_root / "database"
        self.master_path = self.database_root / "master.db"
        self.page_index = self.database_root / "store" / "page"
        self.title_index = self.database_root / "store" / "title"
        self.lucene = lucene_bridge or LuceneReadOnlyBridge(self.installation_root)
        self._validate_installation()

    def _read_json(self, name: str) -> dict[str, Any]:
        path = self.discovery_root / name
        if not path.is_file():
            raise FileNotFoundError(f"DISCOVERY_REPORT_NOT_FOUND:{name}")
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _read_discovery(self) -> dict[str, Any]:
        return self._read_json("shamela-discovery-report.json")

    def _read_locator_proposal(self) -> dict[str, Any]:
        return self._read_json("shamela-locator-proposal.json")

    def _validate_installation(self) -> None:
        if self.discovery.get("installation") != str(self.installation_root):
            raise ValueError("DISCOVERY_INSTALLATION_MISMATCH")
        if self.discovery.get("storage_type") != "HYBRID_SQLITE_AND_LUCENE":
            raise ValueError("DISCOVERY_STORAGE_TYPE_UNSUPPORTED")
        required = (self.master_path, self.page_index, self.title_index)
        if not all(path.exists() for path in required):
            raise FileNotFoundError("SHAMELA_STORAGE_NOT_AVAILABLE")

    def _book_path(self, book_id: int) -> Path:
        return self.database_root / "book" / f"{book_id % 1000:03d}" / f"{book_id}.db"

    @contextmanager
    def _connection(self, path: Path) -> Iterator[sqlite3.Connection]:
        if not path.is_file():
            raise FileNotFoundError(f"SHAMELA_SQLITE_NOT_FOUND:{path.name}")
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            yield connection
        finally:
            connection.close()

    def list_books(
        self,
        *,
        category: str | None = None,
        title: str | None = None,
        author: str | None = None,
        book_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1_000:
            raise ValueError("INVALID_BOOK_LIST_LIMIT")
        clauses, values = [], []
        if book_id is not None:
            clauses.append("b.book_id=?")
            values.append(book_id)
        if category:
            clauses.append("c.category_name LIKE ?")
            values.append(f"%{category}%")
        if title:
            clauses.append("b.book_name LIKE ?")
            values.append(f"%{title}%")
        if author:
            clauses.append("a.author_name LIKE ?")
            values.append(f"%{author}%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = (
            "SELECT b.book_id,b.book_name,c.category_name,a.author_name,b.meta_data "
            "FROM book b LEFT JOIN category c ON c.category_id=b.book_category "
            "LEFT JOIN author a ON a.author_id=b.main_author" + where + " ORDER BY b.book_id LIMIT ?"
        )
        values.append(limit)
        with self._connection(self.master_path) as connection:
            rows = connection.execute(query, values).fetchall()
        return [
            {
                "book_id": row[0], "title": row[1], "category": row[2], "author": row[3],
                "metadata": json.loads(row[4]) if row[4] else {},
                "book_database_available": self._book_path(row[0]).is_file(),
            }
            for row in rows
        ]

    def read_metadata(self, book_id: int) -> dict[str, Any]:
        records = self.list_books(book_id=book_id, limit=1)
        if not records:
            raise KeyError(f"SHAMELA_BOOK_NOT_FOUND:{book_id}")
        record = records[0]
        book_path = self._book_path(book_id)
        if not book_path.is_file():
            raise FileNotFoundError(f"SHAMELA_BOOK_DATABASE_NOT_FOUND:{book_id}")
        record.update(
            {
                "source_type": SOURCE_TYPE,
                "rights_status": RIGHTS_STATUS,
                "database_relative_path": book_path.relative_to(self.installation_root).as_posix(),
                "database_sha256": _hash_file(book_path),
                "installation_fingerprint": self.locator_proposal["installation_fingerprint"],
            }
        )
        return record

    def inspect_book(self, book_id: int) -> dict[str, Any]:
        metadata = self.read_metadata(book_id)
        book_path = self._book_path(book_id)
        with self._connection(book_path) as connection:
            pages = connection.execute("SELECT COUNT(*),COUNT(DISTINCT part),MIN(page),MAX(page) FROM page").fetchone()
            titles = connection.execute("SELECT COUNT(*) FROM title").fetchone()[0]
            encoding = connection.execute("PRAGMA encoding").fetchone()[0]
        return {
            **metadata,
            "page_count": pages[0],
            "volume_count": pages[1],
            "page_min": pages[2],
            "page_max": pages[3],
            "heading_count": titles,
            "encoding": encoding,
        }

    def _locator(self, metadata: dict[str, Any], part: str | None, page: int | None, segment_id: int) -> str:
        volume = part if part not in (None, "") else "0"
        page_value = page if page is not None else segment_id
        return (
            f"shamela://local/{metadata['installation_fingerprint']}/book/{metadata['book_id']}/"
            f"volume/{volume}/page/{page_value}?database_sha256={metadata['database_sha256']}&segment_id={segment_id}"
        )

    @staticmethod
    def _segment_id(book_id: int, lucene_id: str) -> int:
        prefix = f"{book_id}-"
        if not lucene_id.startswith(prefix):
            raise ValueError("LUCENE_DOCUMENT_BOOK_MISMATCH")
        return int(lucene_id[len(prefix):])

    def read_book(self, book_id: int) -> dict[str, Any]:
        metadata = self.read_metadata(book_id)
        book_path = self._book_path(book_id)
        with self._connection(book_path) as connection:
            page_rows = connection.execute("SELECT id,part,page,number FROM page ORDER BY id").fetchall()
            title_rows = connection.execute("SELECT id,page,parent FROM title ORDER BY id").fetchall()
        if len(page_rows) > self.maximum_pages_per_book:
            raise ValueError("PILOT_BOOK_EXCEEDS_PAGE_LIMIT")
        page_documents = self.lucene.read_book(self.page_index, book_id, len(page_rows) + 1)
        title_documents = self.lucene.read_book(self.title_index, book_id, max(len(title_rows) + 1, 1))
        page_by_id = {row[0]: row for row in page_rows}
        title_by_id = {self._segment_id(book_id, item.document_id): item.body for item in title_documents}
        segments, skipped = [], []
        for document in page_documents:
            segment_id = self._segment_id(book_id, document.document_id)
            row = page_by_id.get(segment_id)
            if row is None:
                raise ValueError("LUCENE_PAGE_NOT_IN_SQLITE")
            original_body = document.body
            normalized_body = conservative_normalize(original_body)
            if not normalized_body.strip():
                skipped.append(segment_id)
                continue
            original_foot = document.foot or ""
            segments.append(
                {
                    "segment_id": segment_id,
                    "volume": row[1],
                    "page": row[2],
                    "number": row[3],
                    "locator": self._locator(metadata, row[1], row[2], segment_id),
                    "body_original": original_body,
                    "body_normalized": normalized_body,
                    "foot_original": original_foot,
                    "foot_normalized": conservative_normalize(original_foot),
                }
            )
        segments.sort(key=lambda item: item["segment_id"])
        if not segments:
            raise ValueError("SHAMELA_BOOK_HAS_NO_NONEMPTY_BODY_SEGMENTS")
        headings = []
        for title_id, page_id, parent in title_rows:
            title_text = conservative_normalize(title_by_id.get(title_id, ""))
            if not title_text:
                continue
            page = page_by_id.get(page_id)
            if page is None:
                continue
            headings.append(
                {
                    "heading_id": title_id,
                    "parent_heading_id": parent,
                    "page_segment_id": page_id,
                    "text_original": title_by_id[title_id],
                    "text_normalized": title_text,
                    "locator": self._locator(metadata, page[1], page[2], page_id),
                }
            )
        headings.sort(key=lambda item: item["heading_id"])
        source_locator = self._locator(metadata, segments[0]["volume"], segments[0]["page"], segments[0]["segment_id"])
        content_hash = integrity_hash([
            {"locator": item["locator"], "body": item["body_normalized"], "foot": item["foot_normalized"]}
            for item in segments
        ])
        return {
            "schema_version": STAGING_SCHEMA_VERSION,
            "adapter_version": ADAPTER_VERSION,
            "extracted_at": CANONICAL_TIMESTAMP,
            "source_id": deterministic_id("shamela_local_book", [metadata["installation_fingerprint"], book_id, metadata["database_sha256"], content_hash]),
            "source_type": SOURCE_TYPE,
            "rights_status": RIGHTS_STATUS,
            "source_locator": source_locator,
            "source_metadata": metadata,
            "content_hash": content_hash,
            "page_count": len(page_rows),
            "heading_count": len(headings),
            "segment_count": len(segments),
            "skipped_empty_segment_ids": skipped,
            "headings": headings,
            "segments": segments,
        }

    def stage_book(self, book_id: int, staging_root: str | Path) -> dict[str, Any]:
        root = Path(staging_root).resolve()
        if root == self.installation_root or self.installation_root in root.parents:
            raise ValueError("STAGING_ROOT_MUST_BE_OUTSIDE_SHAMELA")
        book = self.read_book(book_id)
        book_root = root / "books" / str(book_id)
        book_path = book_root / "book.v1.json"
        body_path = book_root / "body.txt"
        body_text = "\n\n".join(
            f"[Shamela locator: {segment['locator']}]\n{segment['body_normalized']}"
            for segment in book["segments"]
        ) + "\n"
        _atomic_write(book_path, _canonical_json(book).encode("utf-8"))
        _atomic_write(body_path, body_text.encode("utf-8"))
        return {
            "book_id": book_id,
            "source_id": book["source_id"],
            "source_locator": book["source_locator"],
            "content_hash": book["content_hash"],
            "book_artifact": book_path.relative_to(root).as_posix(),
            "body_artifact": body_path.relative_to(root).as_posix(),
            "segment_count": book["segment_count"],
            "heading_count": book["heading_count"],
            "page_count": book["page_count"],
            "validation": self.validate_book(book),
        }

    @staticmethod
    def validate_book(book: dict[str, Any]) -> dict[str, Any]:
        segments = book.get("segments", [])
        locators = [item.get("locator", "") for item in segments]
        ids = [item.get("segment_id") for item in segments]
        valid = bool(segments) and len(ids) == len(set(ids)) and len(locators) == len(set(locators))
        valid = valid and all(item.get("body_original") and item.get("body_normalized") and item.get("locator", "").startswith("shamela://local/") for item in segments)
        valid = valid and all(item.get("body_original") != item.get("foot_original", "__missing__") for item in segments if item.get("foot_original"))
        return {
            "status": "VALID" if valid else "INVALID",
            "segment_count": len(segments),
            "duplicate_segment_ids": len(ids) != len(set(ids)),
            "missing_locators": sum(not locator for locator in locators),
            "empty_bodies": sum(not item.get("body_normalized", "").strip() for item in segments),
        }


__all__ = ["ADAPTER_VERSION", "LuceneUnavailableError", "ShamelaLocalSourceAdapter", "conservative_normalize"]
