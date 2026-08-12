"""SIRAJ Luna Research Gateway V4.

Deterministic research-access layer under Luna's direction.

The gateway never decides episode truth. It exposes traceable source operations:
- SEARCH_SHAMELA
- EXPAND_SHAMELA_LOCATOR
- SEARCH_HADITH_LOCAL
- SEARCH_QURAN_CACHE
- MATERIALIZE_QURAN_LOCATOR
- MATERIALIZE_HADITH_URL
- SEARCH_SOURCE_PACKAGES
- GATEWAY_AUDIT

Local operations are offline. Network materialization is opt-in per call and
uses zero automatic retries. Web discovery remains a Luna web_search function,
not an opaque scraper in this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_SHORTLIST = Path(
    r"C:\SIRAJ\Workspace\first-project\working\gold-20-fast-track"
    r"\dynamic-ranking-output\shamela-dynamic-targeted-shortlist.json"
)
SHORTLIST_ENV = "SIRAJ_SHAMELA_SHORTLIST"
MAX_SCAN_BOOKS = 32
MAX_SEARCH_HITS = 160
MAX_HITS_PER_BOOK = 10
MAX_EXCERPT_CHARS = 1800
MAX_EXPAND_ROWS = 15

SHAMELA_LOCATOR_RE = re.compile(
    r"^shamela://local/book/(?P<book_id>\d+)/table/"
    r"(?P<table>[^/]+)/row/(?P<rowid>\d+)$"
)
QURAN_LOCATOR_RE = re.compile(
    r"^(?:Quran\s+)?(?P<surah>\d{1,3}):(?P<start>\d{1,3})"
    r"(?:-(?P<end>\d{1,3}))?$",
    re.I,
)

_STOPWORDS = {
    "هذا", "هذه", "ذلك", "التي", "الذي", "على", "إلى", "الى", "عن", "في",
    "من", "مع", "ثم", "كان", "كانت", "بعد", "قبل", "بين", "أو", "او",
    "ما", "ماذا", "كيف", "لماذا", "حدث", "الحلقة", "التالية", "موضوع",
    "episode", "event", "events", "title", "description",
}

_HADITH_TITLE_HINTS = (
    "حديث", "صحيح", "سنن", "مسند", "موطأ", "مصنف", "جامع", "معجم",
    "hadith", "sahih", "sunan", "musnad",
)

class ResearchGatewayError(RuntimeError):
    pass

@dataclass(frozen=True, slots=True)
class GatewayActionResult:
    operation: str
    status: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status,
            "payload": self.payload,
        }

def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None

def _keywords(value: Mapping[str, Any] | str) -> tuple[str, ...]:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )
    tokens = re.findall(r"[\u0600-\u06ffA-Za-z0-9]{3,}", text)
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        lowered = token.lower()
        if lowered in _STOPWORDS or lowered in seen:
            continue
        seen.add(lowered)
        out.append(token)
    return tuple(out[:40])

def _find_shortlist(repo_root: Path) -> Path | None:
    configured = os.environ.get(SHORTLIST_ENV, "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    repo = repo_root.resolve()
    candidates.extend(
        (
            repo / "sources/shamela/shamela-dynamic-targeted-shortlist.json",
            repo / "data/shamela/shamela-dynamic-targeted-shortlist.json",
            DEFAULT_SHORTLIST,
        )
    )
    for path in candidates:
        if path.is_file():
            return path
    workspace = Path(r"C:\SIRAJ\Workspace")
    if workspace.is_dir():
        try:
            matches = sorted(
                workspace.glob("**/shamela-dynamic-targeted-shortlist.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            matches = []
        if matches:
            return matches[0]
    return None

def _flatten_books(shortlist: Mapping[str, Any]) -> list[dict[str, Any]]:
    books: list[dict[str, Any]] = []
    installations = shortlist.get("installations")
    if not isinstance(installations, list):
        return books
    for installation in installations:
        if not isinstance(installation, Mapping):
            continue
        for item in installation.get("books") or []:
            if not isinstance(item, Mapping):
                continue
            database = str(item.get("book_database") or "").strip()
            if not database:
                continue
            books.append(dict(item))
    return books

def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'

def _text_columns(
    connection: sqlite3.Connection,
    table: str,
) -> tuple[str, ...]:
    preferred = {
        "nass", "text", "content", "matn", "body", "page_text",
        "original_text", "txt", "book_text",
    }
    candidates: list[tuple[int, str]] = []
    try:
        rows = connection.execute(
            f"PRAGMA table_info({_quote_identifier(table)})"
        ).fetchall()
    except sqlite3.Error:
        return ()
    for row in rows:
        name = str(row[1])
        declared = str(row[2] or "").upper()
        lower = name.lower()
        priority = 0
        if lower in preferred:
            priority = 4
        elif any(term in lower for term in ("text", "nass", "matn", "content")):
            priority = 3
        elif any(term in declared for term in ("TEXT", "CHAR", "CLOB")):
            priority = 1
        if priority:
            candidates.append((priority, name))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return tuple(name for _, name in candidates[:6])

def _tables(connection: sqlite3.Connection) -> tuple[str, ...]:
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    except sqlite3.Error:
        return ()
    return tuple(str(row[0]) for row in rows)

def _open_readonly(database: Path) -> sqlite3.Connection:
    if not database.is_file():
        raise ResearchGatewayError(f"SHAMELA_DATABASE_NOT_FOUND:{database}")
    try:
        return sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro",
            uri=True,
        )
    except sqlite3.Error as exc:
        raise ResearchGatewayError(
            f"SHAMELA_DATABASE_OPEN_FAILED:{database}:{exc}"
        ) from exc

class ResearchGatewayV4:
    def __init__(self, repo_root: Path):
        self.repo = repo_root.resolve()
        self.shortlist_path = _find_shortlist(self.repo)
        self._book_cache: list[dict[str, Any]] | None = None

    def books(self) -> list[dict[str, Any]]:
        if self._book_cache is not None:
            return list(self._book_cache)
        if self.shortlist_path is None:
            self._book_cache = []
            return []
        payload = _read_json(self.shortlist_path)
        self._book_cache = _flatten_books(payload or {})
        return list(self._book_cache)

    def _rank_books(
        self,
        query: str,
        *,
        hadith_only: bool = False,
        max_books: int = MAX_SCAN_BOOKS,
    ) -> list[dict[str, Any]]:
        keywords = tuple(token.lower() for token in _keywords(query))
        scored: list[tuple[int, int, str, dict[str, Any]]] = []
        for book in self.books():
            title = str(book.get("title") or "")
            metadata = str(book.get("metadata_excerpt") or "")
            category = str(book.get("category") or "")
            haystack = f"{title} {metadata} {category}".lower()
            if hadith_only and not any(
                hint.lower() in haystack for hint in _HADITH_TITLE_HINTS
            ):
                continue
            overlap = sum(1 for token in keywords if token in haystack)
            documentary = int(book.get("documentary_score", 0) or 0)
            scored.append((overlap, documentary, title, book))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [item[3] for item in scored[:max_books]]

    def _search_book(
        self,
        book: Mapping[str, Any],
        query: str,
        *,
        max_hits: int,
    ) -> list[dict[str, Any]]:
        database = Path(str(book.get("book_database") or ""))
        book_id = int(book.get("book_id", 0) or 0)
        if not database.is_file() or book_id <= 0:
            return []
        keywords = _keywords(query)
        if not keywords:
            return []
        connection = _open_readonly(database)
        hits: list[dict[str, Any]] = []
        seen: set[tuple[str, int, str]] = set()
        try:
            for table in _tables(connection)[:40]:
                for column in _text_columns(connection, table):
                    quoted_table = _quote_identifier(table)
                    quoted_column = _quote_identifier(column)
                    clauses = [f"{quoted_column} LIKE ?" for _ in keywords[:12]]
                    params = ["%" + token + "%" for token in keywords[:12]]
                    if not clauses:
                        continue
                    try:
                        rows = connection.execute(
                            f"SELECT rowid, {quoted_column} "
                            f"FROM {quoted_table} "
                            f"WHERE {quoted_column} IS NOT NULL "
                            f"AND length(trim({quoted_column})) >= 8 "
                            f"AND ({' OR '.join(clauses)}) "
                            f"LIMIT {max_hits}",
                            params,
                        ).fetchall()
                    except sqlite3.Error:
                        continue
                    for rowid, raw in rows:
                        text = re.sub(r"\s+", " ", str(raw)).strip()
                        if not text:
                            continue
                        key = (table, int(rowid), _sha256_text(text))
                        if key in seen:
                            continue
                        seen.add(key)
                        hits.append(
                            {
                                "source_kind": "SHAMELA_LOCAL",
                                "book_id": book_id,
                                "title": str(book.get("title") or ""),
                                "author": str(book.get("author") or ""),
                                "category": str(book.get("category") or ""),
                                "documentary_score": int(
                                    book.get("documentary_score", 0) or 0
                                ),
                                "database_path": str(database),
                                "database_sha256": _sha256_file(database),
                                "table": table,
                                "column": column,
                                "rowid": int(rowid),
                                "locator": (
                                    f"shamela://local/book/{book_id}/"
                                    f"table/{table}/row/{int(rowid)}"
                                ),
                                "text": text[:MAX_EXCERPT_CHARS],
                                "text_sha256": _sha256_text(text),
                            }
                        )
                        if len(hits) >= max_hits:
                            return hits
        finally:
            connection.close()
        return hits

    def search_shamela(
        self,
        query: str,
        *,
        max_books: int = MAX_SCAN_BOOKS,
        max_hits: int = MAX_SEARCH_HITS,
        hadith_only: bool = False,
    ) -> dict[str, Any]:
        if not str(query).strip():
            raise ResearchGatewayError("SEARCH_QUERY_REQUIRED")
        ranked = self._rank_books(
            query,
            hadith_only=hadith_only,
            max_books=max_books,
        )
        results: list[dict[str, Any]] = []
        per_book = max(
            1,
            min(
                MAX_HITS_PER_BOOK,
                max_hits // max(1, len(ranked)),
            ),
        )
        for book in ranked:
            results.extend(
                self._search_book(
                    book,
                    query,
                    max_hits=per_book,
                )
            )
            if len(results) >= max_hits:
                break
        return {
            "schema_version": "siraj-research-gateway-shamela-search-v4",
            "status": "PASS" if results else "NO_MATCH",
            "query": query,
            "keywords": list(_keywords(query)),
            "shortlist_path": (
                str(self.shortlist_path) if self.shortlist_path else None
            ),
            "ranked_book_count": len(ranked),
            "hit_count": len(results[:max_hits]),
            "hits": results[:max_hits],
        }

    def search_hadith_local(
        self,
        query: str,
        *,
        max_books: int = 20,
        max_hits: int = 100,
    ) -> dict[str, Any]:
        result = self.search_shamela(
            query,
            max_books=max_books,
            max_hits=max_hits,
            hadith_only=True,
        )
        result["schema_version"] = (
            "siraj-research-gateway-hadith-local-search-v4"
        )
        result["source_role"] = (
            "LOCAL_HADITH_DISCOVERY_NOT_AUTOMATIC_AUTHENTICATION"
        )
        result["authentication_required"] = True
        return result

    def _book_by_id(self, book_id: int) -> dict[str, Any]:
        matches = [
            book
            for book in self.books()
            if int(book.get("book_id", 0) or 0) == int(book_id)
        ]
        if len(matches) != 1:
            raise ResearchGatewayError(
                f"SHAMELA_BOOK_ID_UNIQUE_REQUIRED:{book_id}:{len(matches)}"
            )
        return matches[0]

    def expand_shamela_locator(
        self,
        locator: str,
        *,
        before: int = 3,
        after: int = 5,
    ) -> dict[str, Any]:
        match = SHAMELA_LOCATOR_RE.fullmatch(str(locator).strip())
        if not match:
            raise ResearchGatewayError(
                f"INVALID_SHAMELA_LOCATOR:{locator}"
            )
        before = max(0, min(int(before), 7))
        after = max(0, min(int(after), 7))
        if before + after + 1 > MAX_EXPAND_ROWS:
            raise ResearchGatewayError("SHAMELA_EXPAND_WINDOW_TOO_LARGE")
        book_id = int(match.group("book_id"))
        table = match.group("table")
        rowid = int(match.group("rowid"))
        book = self._book_by_id(book_id)
        database = Path(str(book.get("book_database") or ""))
        connection = _open_readonly(database)
        rows_out: list[dict[str, Any]] = []
        try:
            tables = set(_tables(connection))
            if table not in tables:
                raise ResearchGatewayError(
                    f"SHAMELA_TABLE_NOT_FOUND:{book_id}:{table}"
                )
            columns = _text_columns(connection, table)
            if not columns:
                raise ResearchGatewayError(
                    f"SHAMELA_TEXT_COLUMNS_NOT_FOUND:{book_id}:{table}"
                )
            quoted_table = _quote_identifier(table)
            select_cols = ", ".join(
                _quote_identifier(column) for column in columns
            )
            start = max(1, rowid - before)
            end = rowid + after
            try:
                rows = connection.execute(
                    f"SELECT rowid, {select_cols} FROM {quoted_table} "
                    f"WHERE rowid BETWEEN ? AND ? ORDER BY rowid",
                    (start, end),
                ).fetchall()
            except sqlite3.Error as exc:
                raise ResearchGatewayError(
                    f"SHAMELA_EXPAND_QUERY_FAILED:{exc}"
                ) from exc
            for row in rows:
                rid = int(row[0])
                parts = [
                    re.sub(r"\s+", " ", str(value)).strip()
                    for value in row[1:]
                    if value not in (None, "")
                ]
                text = " | ".join(part for part in parts if part)
                if not text:
                    continue
                rows_out.append(
                    {
                        "rowid": rid,
                        "is_anchor_row": rid == rowid,
                        "locator": (
                            f"shamela://local/book/{book_id}/"
                            f"table/{table}/row/{rid}"
                        ),
                        "text": text[:MAX_EXCERPT_CHARS],
                        "text_sha256": _sha256_text(text),
                    }
                )
        finally:
            connection.close()
        return {
            "schema_version": "siraj-research-gateway-shamela-expand-v4",
            "status": "PASS" if rows_out else "NO_CONTEXT",
            "book_id": book_id,
            "title": str(book.get("title") or ""),
            "author": str(book.get("author") or ""),
            "database_path": str(database),
            "database_sha256": _sha256_file(database),
            "anchor_locator": locator,
            "window": {"before": before, "after": after},
            "rows": rows_out,
        }

    def search_quran_cache(
        self,
        query: str,
        *,
        limit: int = 80,
    ) -> dict[str, Any]:
        keywords = tuple(token.lower() for token in _keywords(query))
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        patterns = (
            "projects/episode-*/evidence/quran-source-materialization*.json",
            "sources/quran/**/*.json",
            "data/quran/**/*.json",
        )
        candidates: list[Path] = []
        for pattern in patterns:
            candidates.extend(self.repo.glob(pattern))
        for path in sorted(set(candidates)):
            payload = _read_json(path)
            if payload is None:
                continue
            raw_records = payload.get("source_records")
            if not isinstance(raw_records, list):
                raw_records = payload.get("verses")
            if not isinstance(raw_records, list):
                continue
            for item in raw_records:
                if not isinstance(item, Mapping):
                    continue
                text = str(
                    item.get("arabic_anchor_text")
                    or item.get("text_uthmani")
                    or item.get("text")
                    or ""
                )
                locator = str(
                    item.get("locator")
                    or item.get("verse_key")
                    or item.get("source_url")
                    or ""
                )
                haystack = (
                    text
                    + " "
                    + locator
                    + " "
                    + json.dumps(item, ensure_ascii=False)
                ).lower()
                if keywords and not any(
                    token in haystack for token in keywords
                ):
                    continue
                key = str(
                    item.get("source_record_id")
                    or item.get("verse_key")
                    or locator
                    or _sha256_text(text)
                )
                if key in seen:
                    continue
                seen.add(key)
                records.append(
                    {
                        "source_kind": "QURAN_CACHE",
                        "cache_path": str(path),
                        "record": dict(item),
                        "text_sha256": _sha256_text(text) if text else None,
                        "reuse_policy": (
                            "DISCOVERY_OR_PRIMARY_TEXT_REFERENCE;"
                            "REVERIFY_LOCATOR_FOR_NEW_EPISODE"
                        ),
                    }
                )
                if len(records) >= limit:
                    break
            if len(records) >= limit:
                break
        return {
            "schema_version": "siraj-research-gateway-quran-cache-search-v4",
            "status": "PASS" if records else "NO_MATCH",
            "query": query,
            "record_count": len(records),
            "records": records,
            "completeness": "CACHE_NOT_ASSUMED_COMPLETE_QURAN_CORPUS",
        }

    def search_source_packages(
        self,
        query: str,
        *,
        limit: int = 80,
    ) -> dict[str, Any]:
        keywords = tuple(token.lower() for token in _keywords(query))
        results: list[dict[str, Any]] = []
        for path in sorted(
            self.repo.glob(
                "projects/episode-*/contracts/source-package-v1*.json"
            )
        ):
            payload = _read_json(path)
            if payload is None:
                continue
            items = payload.get("source_items")
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                serialized = json.dumps(item, ensure_ascii=False)
                if keywords and not any(
                    token in serialized.lower() for token in keywords
                ):
                    continue
                results.append(
                    {
                        "source_kind": "PRIOR_SOURCE_PACKAGE_LEAD",
                        "package_path": str(path),
                        "item": dict(item),
                        "reuse_policy": (
                            "DISCOVERY_LEAD_ONLY_REVERIFY_BEFORE_CLAIM_BINDING"
                        ),
                    }
                )
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        return {
            "schema_version": (
                "siraj-research-gateway-source-package-search-v4"
            ),
            "status": "PASS" if results else "NO_MATCH",
            "query": query,
            "result_count": len(results),
            "results": results,
        }

    def materialize_quran_locator(
        self,
        locator: str,
        *,
        allow_network: bool,
    ) -> dict[str, Any]:
        if not allow_network:
            raise ResearchGatewayError(
                "NETWORK_SOURCE_MATERIALIZATION_NOT_AUTHORIZED"
            )
        match = QURAN_LOCATOR_RE.fullmatch(str(locator).strip())
        if not match:
            raise ResearchGatewayError(
                f"INVALID_QURAN_LOCATOR:{locator}"
            )
        from src.application.storyboard_runtime.remote_source_materialization import (
            default_fetcher,
            parse_quran_api_response,
            quran_request_urls,
        )
        surah = int(match.group("surah"))
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        if end < start or end - start > 20:
            raise ResearchGatewayError("QURAN_RANGE_INVALID")
        verses: list[dict[str, Any]] = []
        for ayah in range(start, end + 1):
            verse_key = f"{surah}:{ayah}"
            attempts: list[dict[str, Any]] = []
            extracted = ""
            selected_url = ""
            for url in quran_request_urls(verse_key):
                result = default_fetcher(
                    url,
                    timeout_seconds=30,
                    retries=0,
                )
                raw = result.pop("response_bytes")
                attempts.append(
                    {
                        key: value
                        for key, value in result.items()
                        if key != "errors"
                    }
                    | {"errors": result.get("errors", [])}
                )
                if not result.get("success"):
                    continue
                text = parse_quran_api_response(raw, verse_key)
                if text:
                    extracted = text
                    selected_url = str(
                        result.get("final_url") or url
                    )
                    break
            verses.append(
                {
                    "verse_key": verse_key,
                    "status": "PASS" if extracted else "FETCH_OR_EXTRACTION_FAILED",
                    "locator": f"Quran {verse_key}",
                    "source_url": selected_url,
                    "text_uthmani": extracted,
                    "text_sha256": (
                        _sha256_text(extracted) if extracted else None
                    ),
                    "attempts": attempts,
                    "automatic_retry": False,
                }
            )
        return {
            "schema_version": (
                "siraj-research-gateway-quran-materialization-v4"
            ),
            "status": (
                "PASS"
                if verses
                and all(item["status"] == "PASS" for item in verses)
                else "PARTIAL_OR_FAILED"
            ),
            "requested_locator": locator,
            "verses": verses,
            "network": True,
            "automatic_retry": False,
        }

    def materialize_hadith_url(
        self,
        url: str,
        *,
        arabic_anchor_text: str,
        allow_network: bool,
    ) -> dict[str, Any]:
        if not allow_network:
            raise ResearchGatewayError(
                "NETWORK_SOURCE_MATERIALIZATION_NOT_AUTHORIZED"
            )
        if not str(url).startswith(("https://", "http://")):
            raise ResearchGatewayError("HADITH_URL_HTTP_REQUIRED")
        if not str(arabic_anchor_text).strip():
            raise ResearchGatewayError("HADITH_ARABIC_ANCHOR_REQUIRED")
        from src.application.storyboard_runtime.remote_source_materialization import (
            choose_hadith_arabic_block,
            default_fetcher,
        )
        retrieval = default_fetcher(
            url,
            timeout_seconds=30,
            retries=0,
        )
        raw = retrieval.pop("response_bytes")
        extraction = (
            choose_hadith_arabic_block(
                raw,
                arabic_anchor_text,
            )
            if retrieval.get("success")
            else {
                "success": False,
                "error": "FETCH_FAILED",
                "machine_extracted_text": "",
                "metrics": {},
                "selected_block": None,
            }
        )
        text = str(extraction.get("machine_extracted_text") or "")
        return {
            "schema_version": (
                "siraj-research-gateway-hadith-materialization-v4"
            ),
            "status": (
                "PASS"
                if retrieval.get("success")
                and extraction.get("success")
                else "FAILED"
            ),
            "requested_url": url,
            "retrieval": retrieval,
            "extraction": extraction,
            "text_sha256": _sha256_text(text) if text else None,
            "authentication_status": "NOT_AUTHENTICATED_BY_EXTRACTION_ALONE",
            "automatic_retry": False,
        }

    def audit(self) -> dict[str, Any]:
        books = self.books()
        existing_databases = sum(
            Path(str(book.get("book_database") or "")).is_file()
            for book in books
        )
        hadith_candidates = 0
        for book in books:
            haystack = (
                str(book.get("title") or "")
                + " "
                + str(book.get("category") or "")
            ).lower()
            if any(hint.lower() in haystack for hint in _HADITH_TITLE_HINTS):
                hadith_candidates += 1
        quran_cache_files = list(
            self.repo.glob(
                "projects/episode-*/evidence/"
                "quran-source-materialization*.json"
            )
        )
        source_packages = list(
            self.repo.glob(
                "projects/episode-*/contracts/"
                "source-package-v1*.json"
            )
        )
        return {
            "schema_version": "siraj-research-gateway-audit-v4",
            "status": (
                "READY_LOCAL"
                if self.shortlist_path
                and existing_databases > 0
                else "LOCAL_SOURCE_SETUP_INCOMPLETE"
            ),
            "shortlist_path": (
                str(self.shortlist_path)
                if self.shortlist_path
                else None
            ),
            "shortlist_book_count": len(books),
            "existing_database_count": existing_databases,
            "hadith_candidate_book_count": hadith_candidates,
            "quran_cache_file_count": len(quran_cache_files),
            "prior_source_package_count": len(source_packages),
            "operations": [
                "SEARCH_SHAMELA",
                "EXPAND_SHAMELA_LOCATOR",
                "SEARCH_HADITH_LOCAL",
                "SEARCH_QURAN_CACHE",
                "MATERIALIZE_QURAN_LOCATOR",
                "MATERIALIZE_HADITH_URL",
                "SEARCH_SOURCE_PACKAGES",
                "SEARCH_WEB_GAP_VIA_LUNA_WEB_SEARCH",
            ],
            "network_default": "BLOCKED",
            "network_materialization": (
                "EXPLICIT_ALLOW_NETWORK_PER_CALL"
            ),
            "automatic_network_retry": False,
        }

    def execute(
        self,
        action: Mapping[str, Any],
        *,
        allow_network: bool = False,
    ) -> GatewayActionResult:
        operation = str(action.get("operation") or "").upper()
        query = str(action.get("query") or "")
        params = action.get("params")
        params = dict(params) if isinstance(params, Mapping) else {}

        if operation == "SEARCH_SHAMELA":
            payload = self.search_shamela(
                query,
                max_books=int(params.get("max_books", MAX_SCAN_BOOKS)),
                max_hits=int(params.get("max_hits", MAX_SEARCH_HITS)),
            )
        elif operation == "EXPAND_SHAMELA_LOCATOR":
            payload = self.expand_shamela_locator(
                str(action.get("locator") or ""),
                before=int(params.get("before", 3)),
                after=int(params.get("after", 5)),
            )
        elif operation == "SEARCH_HADITH_LOCAL":
            payload = self.search_hadith_local(
                query,
                max_books=int(params.get("max_books", 20)),
                max_hits=int(params.get("max_hits", 100)),
            )
        elif operation == "SEARCH_QURAN_CACHE":
            payload = self.search_quran_cache(
                query,
                limit=int(params.get("limit", 80)),
            )
        elif operation == "MATERIALIZE_QURAN_LOCATOR":
            payload = self.materialize_quran_locator(
                str(action.get("locator") or ""),
                allow_network=allow_network,
            )
        elif operation == "MATERIALIZE_HADITH_URL":
            payload = self.materialize_hadith_url(
                str(action.get("url") or ""),
                arabic_anchor_text=str(
                    action.get("arabic_anchor_text") or ""
                ),
                allow_network=allow_network,
            )
        elif operation == "SEARCH_SOURCE_PACKAGES":
            payload = self.search_source_packages(
                query,
                limit=int(params.get("limit", 80)),
            )
        elif operation == "GATEWAY_AUDIT":
            payload = self.audit()
        elif operation == "SEARCH_WEB_GAP":
            payload = {
                "schema_version": (
                    "siraj-research-gateway-web-delegation-v4"
                ),
                "status": "DELEGATE_TO_LUNA_WEB_SEARCH",
                "query": query,
                "rule": (
                    "WEB_SEARCH_IS_A_LUNA_RESEARCH_TOOL;"
                    "RAW_FETCH_MAY_BE_MATERIALIZED_AFTER_SELECTION"
                ),
            }
        else:
            raise ResearchGatewayError(
                f"UNSUPPORTED_RESEARCH_OPERATION:{operation}"
            )
        return GatewayActionResult(
            operation=operation,
            status=str(payload.get("status") or "UNKNOWN"),
            payload=payload,
        )

def audit_gateway(repo_root: Path) -> dict[str, Any]:
    return ResearchGatewayV4(repo_root).audit()
