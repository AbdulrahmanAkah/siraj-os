from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

TARGET_SOURCE_ID = "SRC-HISTORY-BIDAYAH-ADAM"
TARGET_BOOK_ID = 4445


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def qid(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def first_value(mapping: dict[str, Any], names: Iterable[str]) -> Any:
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def walk(value: Any, inherited_source_id: str | None = None):
    if isinstance(value, dict):
        local_source = first_value(
            value,
            ("source_id", "sourceId", "work_source_id", "target_source_id"),
        )
        source_id = str(local_source) if local_source is not None else inherited_source_id
        book_id = first_value(value, ("book_id", "bookId", "id", "selected_book_id"))
        title = first_value(value, ("title", "book_title", "book_name", "name"))
        if book_id is not None and title is not None:
            yield source_id, value
        for child in value.values():
            yield from walk(child, source_id)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child, inherited_source_id)


def to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def collect_candidates(report: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for inherited_source, mapping in walk(report):
        book_id = to_int(first_value(mapping, ("book_id", "bookId", "id", "selected_book_id")))
        if book_id is None:
            continue
        source = first_value(mapping, ("source_id", "sourceId", "work_source_id", "target_source_id"))
        source_id = str(source) if source is not None else inherited_source
        title = str(first_value(mapping, ("title", "book_title", "book_name", "name")) or "")
        author = str(first_value(mapping, ("author", "author_name", "main_author_name")) or "")
        raw_score = first_value(mapping, ("score", "match_score", "ranking_score"))
        try:
            score = float(raw_score) if raw_score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        found.append(
            {
                "source_id": source_id,
                "book_id": book_id,
                "title": title,
                "author": author,
                "score": score,
            }
        )

    target = [item for item in found if item["source_id"] == TARGET_SOURCE_ID]
    if not target:
        target = [
            item for item in found
            if "البداية والنهاية" in item["title"]
            or ("بداية" in item["title"] and "نهاية" in item["title"])
        ]

    deduped: dict[int, dict[str, Any]] = {}
    for item in target:
        previous = deduped.get(item["book_id"])
        if previous is None or item["score"] > previous["score"]:
            deduped[item["book_id"]] = item
    return sorted(deduped.values(), key=lambda item: (-item["score"], item["book_id"]))


def build_db_index(book_root: Path) -> dict[int, Path]:
    index: dict[int, Path] = {}
    if not book_root.is_dir():
        return index
    for path in book_root.rglob("*.db"):
        try:
            book_id = int(path.stem)
        except ValueError:
            continue
        index.setdefault(book_id, path)
    return index


def preview(value: Any, limit: int = 8000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value[:limit].decode("utf-8", errors="ignore")
    return str(value)[:limit]


def inspect_database(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "path": None if path is None else str(path),
            "exists": False,
            "storage_class": "MISSING_DATABASE",
            "text_candidates": [],
        }

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()]
        if integrity != ["ok"]:
            return {
                "path": str(path),
                "exists": True,
                "integrity_check": integrity,
                "storage_class": "SQLITE_INTEGRITY_FAILURE",
                "text_candidates": [],
            }

        candidates: list[dict[str, Any]] = []
        objects = connection.execute(
            """
            SELECT type, name FROM sqlite_master
            WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        for obj in objects:
            table = str(obj["name"])
            columns = [
                {"name": str(row[1]), "declared_type": str(row[2] or "")}
                for row in connection.execute(f"PRAGMA table_info({qid(table)})").fetchall()
            ]
            for column in columns:
                name = column["name"]
                try:
                    stats = connection.execute(
                        f"""
                        SELECT MAX(LENGTH({qid(name)})), AVG(LENGTH({qid(name)}))
                        FROM {qid(table)}
                        WHERE {qid(name)} IS NOT NULL
                        """
                    ).fetchone()
                    samples = connection.execute(
                        f"""
                        SELECT {qid(name)}
                        FROM {qid(table)}
                        WHERE {qid(name)} IS NOT NULL
                        ORDER BY LENGTH({qid(name)}) DESC
                        LIMIT 8
                        """
                    ).fetchall()
                except sqlite3.DatabaseError:
                    continue

                max_length = int(stats[0] or 0)
                avg_length = float(stats[1] or 0.0)
                sample_text = "\n".join(preview(row[0]) for row in samples)
                arabic_chars = len(re.findall(r"[\u0600-\u06FF]", sample_text))
                if max_length >= 250 and arabic_chars >= 100:
                    candidates.append(
                        {
                            "table": table,
                            "column": name,
                            "declared_type": column["declared_type"],
                            "max_length": max_length,
                            "avg_length": round(avg_length, 2),
                            "sample_arabic_chars": arabic_chars,
                        }
                    )

        candidates.sort(
            key=lambda item: (
                -item["sample_arabic_chars"],
                -item["max_length"],
                item["table"],
                item["column"],
            )
        )
        return {
            "path": str(path),
            "exists": True,
            "integrity_check": integrity,
            "storage_class": "TEXT_DATABASE" if candidates else "NO_TEXT_BODY_DETECTED",
            "text_candidates": candidates,
        }
    finally:
        connection.close()


def master_metadata(connection: sqlite3.Connection, book_id: int) -> dict[str, Any]:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "book" not in tables:
        return {}
    columns = [str(row[1]) for row in connection.execute('PRAGMA table_info("book")')]
    id_column = next((name for name in columns if name.lower() in {"book_id", "id", "bookid"}), None)
    if id_column is None:
        return {}
    row = connection.execute(
        f'SELECT * FROM "book" WHERE CAST({qid(id_column)} AS TEXT) = ? LIMIT 1',
        (str(book_id),),
    ).fetchone()
    return {} if row is None else {key: row[key] for key in row.keys()}


def classify(db_report: dict[str, Any], metadata: dict[str, Any]) -> str:
    if db_report["storage_class"] == "TEXT_DATABASE":
        return "TEXT_DATABASE"
    pdf_links = metadata.get("pdf_links")
    if pdf_links:
        db_report["pdf_links"] = pdf_links
        db_report["pdf_ondisk"] = metadata.get("pdf_ondisk")
        if str(metadata.get("pdf_ondisk")) in {"0", "False", "false", "None"}:
            return "PDF_INDEX_ONLY_REMOTE_PDF"
        return "PDF_INDEX_WITH_LOCAL_PDF"
    return db_report["storage_class"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--shamela-root", default=r"C:\shamela4")
    parser.add_argument("--master-db", default=r"C:\shamela4\database\master.db")
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    secondary = repo / "projects" / "episode-001-adam" / "sources" / "secondary"
    report_path = secondary / "shamela-book-candidates-v1.json"
    if not report_path.is_file():
        raise SystemExit(f"CANDIDATE_REPORT_MISSING:{report_path}")

    candidates = collect_candidates(read_json(report_path))
    if not candidates:
        raise SystemExit("NO_BIDAYAH_CANDIDATES_FOUND")

    db_index = build_db_index(Path(args.shamela_root) / "database" / "book")
    master_path = Path(args.master_db)
    if not master_path.is_file():
        raise SystemExit(f"MASTER_DATABASE_MISSING:{master_path}")

    master = sqlite3.connect(str(master_path))
    master.row_factory = sqlite3.Row
    reports: list[dict[str, Any]] = []
    try:
        for candidate in candidates:
            book_id = candidate["book_id"]
            db_report = inspect_database(db_index.get(book_id))
            metadata = master_metadata(master, book_id)
            reports.append(
                {
                    **candidate,
                    "database": db_report,
                    "storage_class": classify(db_report, metadata),
                    "master_metadata": {
                        "book_name": metadata.get("book_name"),
                        "pdf_ondisk": metadata.get("pdf_ondisk"),
                        "pdf_online": metadata.get("pdf_online"),
                        "major_ondisk": metadata.get("major_ondisk"),
                        "major_online": metadata.get("major_online"),
                    },
                }
            )
    finally:
        master.close()

    text_reports = [item for item in reports if item["storage_class"] == "TEXT_DATABASE"]
    text_reports.sort(key=lambda item: (-item["score"], item["book_id"]))
    if text_reports:
        best = text_reports[0]
        recommendation = {
            "status": "RECOMMENDED_TEXT_REPLACEMENT",
            "book_id": best["book_id"],
            "title": best["title"],
            "author": best["author"],
            "candidate_score": best["score"],
            "database_path": best["database"]["path"],
            "best_text_mapping": best["database"]["text_candidates"][0],
            "reason": "Highest-ranked local candidate with verified Arabic long text. Human confirmation remains required.",
        }
        next_gate = "HUMAN_REPLACEMENT_SELECTION"
    else:
        recommendation = {
            "status": "NO_LOCAL_TEXT_REPLACEMENT_FOUND",
            "reason": "No ranked local candidate contains verified Arabic long text. Controlled PDF acquisition is required.",
        }
        next_gate = "CONTROLLED_PDF_ACQUISITION_DECISION"

    output = {
        "schema_version": "siraj-bidayah-text-candidate-scan-v1",
        "created_at": now_utc(),
        "target_source_id": TARGET_SOURCE_ID,
        "current_selected_book_id": TARGET_BOOK_ID,
        "current_selected_storage_class": next(
            (item["storage_class"] for item in reports if item["book_id"] == TARGET_BOOK_ID),
            "NOT_PRESENT",
        ),
        "candidate_count": len(reports),
        "text_database_count": len(text_reports),
        "candidates": reports,
        "recommendation": recommendation,
        "permissions": {
            "selection_changed": False,
            "raw_asset_changed": False,
            "gemini_execution_enabled": False,
            "source_approval_changed": False,
        },
        "next_gate": next_gate,
    }

    output_path = secondary / "diagnostics" / "bidayah-text-candidate-scan-v1.json"
    write_json(output_path, output)

    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output_path),
                "candidate_count": len(reports),
                "text_database_count": len(text_reports),
                "current_selected_storage_class": output["current_selected_storage_class"],
                "recommendation": recommendation,
                "selection_changed": False,
                "gemini_execution_enabled": False,
                "next_gate": next_gate,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
