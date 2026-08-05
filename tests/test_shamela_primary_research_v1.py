from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.application.shamela_primary_research_v1 import (
    build_shamela_primary_context,
    require_shamela_primary_context,
)


def _book(path: Path, texts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE pages(id INTEGER PRIMARY KEY, nass TEXT)"
        )
        for text in texts:
            connection.execute("INSERT INTO pages(nass) VALUES(?)", (text,))
        connection.commit()
    finally:
        connection.close()


def test_local_shamela_context_is_primary(tmp_path: Path, monkeypatch) -> None:
    books = []
    for index in range(1, 4):
        database = tmp_path / "books" / f"{index}.db"
        _book(
            database,
            [
                f"نص تاريخي موثق عن آدم والخلق والحدث رقم {index}.",
                f"تفصيل إضافي عن آدم وتسلسل القصة في المصدر {index}.",
            ],
        )
        books.append(
            {
                "book_id": index,
                "title": f"كتاب تاريخ آدم {index}",
                "author": "مؤلف",
                "category": "التاريخ",
                "documentary_score": 20,
                "book_database": str(database),
                "book_database_exists": True,
            }
        )
    shortlist = tmp_path / "shortlist.json"
    shortlist.write_text(
        json.dumps(
            {"installations": [{"books": books}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SIRAJ_SHAMELA_SHORTLIST", str(shortlist))
    context = require_shamela_primary_context(
        tmp_path,
        {"topic_title_ar": "قصة آدم", "events": [{"title_ar": "خلق آدم"}]},
    )
    assert context["status"] == "READY"
    assert context["source_priority"] == (
        "SHAMELA_PRIMARY_INTERNET_SECONDARY"
    )
    assert context["books_with_excerpts"] == 3
    assert context["excerpt_count"] >= 6
    assert all(
        excerpt["locator"].startswith("shamela://local/")
        for source in context["sources"]
        for excerpt in source["excerpts"]
    )


def test_catalog_context_can_drive_scope_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shortlist = tmp_path / "shortlist.json"
    shortlist.write_text(
        json.dumps(
            {
                "installations": [
                    {
                        "books": [
                            {
                                "book_id": index,
                                "title": f"كتاب السيرة {index}",
                                "documentary_score": 10,
                                "book_database": str(
                                    tmp_path / f"missing-{index}.db"
                                ),
                                "book_database_exists": True,
                            }
                            for index in range(1, 4)
                        ]
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SIRAJ_SHAMELA_SHORTLIST", str(shortlist))
    context = build_shamela_primary_context(
        tmp_path,
        "السيرة",
        require_excerpts=False,
    )
    assert context["status"] == "READY"
    assert context["selected_book_count"] == 3
