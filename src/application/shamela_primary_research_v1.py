from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping

DEFAULT_SHORTLIST = Path(
    r"C:\SIRAJ\Workspace\first-project\working\gold-20-fast-track"
    r"\dynamic-ranking-output\shamela-dynamic-targeted-shortlist.json"
)
MAX_BOOKS = 12
MAX_EXCERPTS_PER_BOOK = 4
MAX_EXCERPT_CHARS = 700
MIN_BOOKS_WITH_EXCERPTS = 3
MIN_EXCERPTS = 6

_STOPWORDS = {
    "هذا", "هذه", "ذلك", "التي", "الذي", "على", "إلى", "الى", "عن", "في",
    "من", "مع", "ثم", "كان", "كانت", "بعد", "قبل", "بين", "أو", "او",
    "ما", "ماذا", "كيف", "لماذا", "حدث", "الحلقة", "التالية", "موضوع",
    "episode", "event", "events", "title", "description",
}


class ShamelaPrimarySourceError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _find_shortlist(repo_root: Path) -> Path | None:
    candidates = []
    configured = os.environ.get("SIRAJ_SHAMELA_SHORTLIST", "").strip()
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        (
            repo_root.resolve()
            / "sources/shamela/shamela-dynamic-targeted-shortlist.json",
            repo_root.resolve()
            / "data/shamela/shamela-dynamic-targeted-shortlist.json",
            DEFAULT_SHORTLIST,
        )
    )
    for path in candidates:
        if path.is_file():
            return path
    workspace = Path(r"C:\SIRAJ\Workspace")
    if workspace.is_dir():
        matches = sorted(
            workspace.glob("**/shamela-dynamic-targeted-shortlist.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]
    return None


def _keywords(value: Mapping[str, Any] | str) -> tuple[str, ...]:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )
    tokens = re.findall(r"[\u0600-\u06ffA-Za-z0-9]{3,}", text)
    result: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        key = token.lower()
        if key in _STOPWORDS or key in seen:
            continue
        seen.add(key)
        result.append(token)
    return tuple(result[:24])


def _books(shortlist: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    installations = shortlist.get("installations")
    if not isinstance(installations, list):
        return result
    for installation in installations:
        if not isinstance(installation, Mapping):
            continue
        items = installation.get("books")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            database = str(item.get("book_database", "")).strip()
            if database:
                result.append(dict(item))
    return result


def _rank(
    books: list[dict[str, Any]],
    keywords: tuple[str, ...],
) -> list[dict[str, Any]]:
    lowered = [item.lower() for item in keywords]
    scored = []
    for book in books:
        title = str(book.get("title", ""))
        metadata = str(book.get("metadata_excerpt", ""))
        haystack = (title + " " + metadata).lower()
        overlap = sum(1 for token in lowered if token in haystack)
        score = int(book.get("documentary_score", 0) or 0)
        scored.append((overlap, score, title, book))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[3] for item in scored[:MAX_BOOKS]]


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _text_columns(
    connection: sqlite3.Connection,
    table: str,
) -> tuple[str, ...]:
    preferred = {
        "nass", "text", "content", "matn", "body", "page_text",
        "original_text", "txt", "book_text",
    }
    columns = []
    for row in connection.execute(
        f"PRAGMA table_info({_quote(table)})"
    ).fetchall():
        name = str(row[1])
        declared = str(row[2] or "").upper()
        lowered = name.lower()
        priority = 0
        if lowered in preferred:
            priority = 3
        elif any(term in lowered for term in ("text", "nass", "matn", "content")):
            priority = 2
        elif any(term in declared for term in ("TEXT", "CHAR", "CLOB")):
            priority = 1
        if priority:
            columns.append((priority, name))
    columns.sort(key=lambda item: (-item[0], item[1]))
    return tuple(name for _, name in columns[:4])


def _extract_book(
    book: Mapping[str, Any],
    keywords: tuple[str, ...],
) -> dict[str, Any]:
    database = Path(str(book.get("book_database", "")))
    book_id = int(book.get("book_id", 0) or 0)
    result = {
        "local_source_key": f"SHAMELA-BOOK-{book_id}",
        "book_id": book_id,
        "title": str(book.get("title", "")),
        "author": str(book.get("author", "")),
        "category": str(book.get("category", "")),
        "book_database": str(database),
        "excerpts": [],
    }
    if not database.is_file():
        return result
    try:
        connection = sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro",
            uri=True,
        )
    except sqlite3.Error:
        return result
    try:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
        ]
        excerpts = []
        for table in tables[:20]:
            for column in _text_columns(connection, table):
                quoted_table = _quote(table)
                quoted_column = _quote(column)
                clauses = [f"{quoted_column} LIKE ?" for _ in keywords[:8]]
                params = ["%" + token + "%" for token in keywords[:8]]
                rows = []
                if clauses:
                    try:
                        rows = connection.execute(
                            f"SELECT rowid, {quoted_column} "
                            f"FROM {quoted_table} "
                            f"WHERE {quoted_column} IS NOT NULL "
                            f"AND length({quoted_column}) >= 40 "
                            f"AND ({' OR '.join(clauses)}) "
                            f"LIMIT {MAX_EXCERPTS_PER_BOOK}",
                            params,
                        ).fetchall()
                    except sqlite3.Error:
                        rows = []
                if not rows:
                    try:
                        rows = connection.execute(
                            f"SELECT rowid, {quoted_column} "
                            f"FROM {quoted_table} "
                            f"WHERE {quoted_column} IS NOT NULL "
                            f"AND length({quoted_column}) >= 40 "
                            f"LIMIT 2"
                        ).fetchall()
                    except sqlite3.Error:
                        rows = []
                for rowid, raw in rows:
                    text = re.sub(r"\s+", " ", str(raw)).strip()
                    if text:
                        excerpts.append(
                            {
                                "locator": (
                                    f"shamela://local/book/{book_id}/"
                                    f"table/{table}/row/{rowid}"
                                ),
                                "text": text[:MAX_EXCERPT_CHARS],
                            }
                        )
                if len(excerpts) >= MAX_EXCERPTS_PER_BOOK:
                    break
            if len(excerpts) >= MAX_EXCERPTS_PER_BOOK:
                break
        result["excerpts"] = excerpts[:MAX_EXCERPTS_PER_BOOK]
    finally:
        connection.close()
    return result


def _package_sources(
    repo_root: Path,
    keywords: tuple[str, ...],
) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(
        repo_root.resolve().glob(
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
                token.lower() in serialized.lower()
                for token in keywords[:12]
            ):
                continue
            locators = re.findall(r"shamela://local/[^\"\s]+", serialized)
            texts = [
                value.strip()
                for value in item.values()
                if isinstance(value, str) and len(value.strip()) >= 40
            ]
            if not locators and not texts:
                continue
            entries.append(
                {
                    "local_source_key": str(
                        item.get("source_id")
                        or item.get("id")
                        or f"PACKAGE-{len(entries) + 1}"
                    ),
                    "book_id": item.get("book_id"),
                    "title": str(
                        item.get("title")
                        or item.get("source_title")
                        or path.stem
                    ),
                    "author": str(item.get("author", "")),
                    "category": "SOURCE_PACKAGE",
                    "book_database": "",
                    "excerpts": [
                        {
                            "locator": (
                                locators[0]
                                if locators
                                else f"shamela://local/source-package/{path.stem}"
                            ),
                            "text": text[:MAX_EXCERPT_CHARS],
                        }
                        for text in texts[:2]
                    ],
                }
            )
            if len(entries) >= MAX_BOOKS:
                return entries
    return entries


def build_shamela_primary_context(
    repo_root: Path,
    query_payload: Mapping[str, Any] | str,
    *,
    require_excerpts: bool,
) -> dict[str, Any]:
    keywords = _keywords(query_payload)
    shortlist_path = _find_shortlist(repo_root)
    selected = []
    if shortlist_path is not None:
        shortlist = _read_json(shortlist_path)
        if shortlist is not None:
            selected = _rank(_books(shortlist), keywords)

    merged = _package_sources(repo_root, keywords)
    merged.extend(_extract_book(book, keywords) for book in selected)
    unique = {}
    for item in merged:
        key = str(item.get("local_source_key", ""))
        if key and key not in unique:
            unique[key] = item
    sources = list(unique.values())[:MAX_BOOKS]
    excerpt_count = sum(
        len(item.get("excerpts", []))
        for item in sources
        if isinstance(item.get("excerpts"), list)
    )
    books_with_excerpts = sum(
        1
        for item in sources
        if isinstance(item.get("excerpts"), list)
        and item.get("excerpts")
    )
    if require_excerpts:
        ready = (
            books_with_excerpts >= MIN_BOOKS_WITH_EXCERPTS
            and excerpt_count >= MIN_EXCERPTS
        )
        status = "READY" if ready else "INSUFFICIENT"
    else:
        status = "READY" if len(sources) >= 3 else "CATALOG_INSUFFICIENT"
    return {
        "schema_version": "siraj-shamela-primary-context-v1",
        "status": status,
        "source_priority": "SHAMELA_PRIMARY_INTERNET_SECONDARY",
        "shortlist_path": str(shortlist_path) if shortlist_path else None,
        "query_keywords": list(keywords),
        "selected_book_count": len(sources),
        "books_with_excerpts": books_with_excerpts,
        "excerpt_count": excerpt_count,
        "sources": sources,
        "internet_policy": (
            "WEB_SEARCH_ALLOWED_ONLY_FOR_EXPLICIT_GAPS_NOT_COVERED_"
            "BY_SELECTED_SHAMELA_BOOKS"
        ),
    }


def require_shamela_primary_context(
    repo_root: Path,
    query_payload: Mapping[str, Any] | str,
) -> dict[str, Any]:
    context = build_shamela_primary_context(
        repo_root,
        query_payload,
        require_excerpts=True,
    )
    if context["status"] != "READY":
        raise ShamelaPrimarySourceError(
            "SHAMELA_PRIMARY_CONTEXT_INSUFFICIENT:"
            f"books={context['books_with_excerpts']}:"
            f"excerpts={context['excerpt_count']}:"
            f"shortlist={context['shortlist_path']}"
        )
    return context
