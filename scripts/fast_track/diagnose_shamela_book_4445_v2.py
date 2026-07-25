from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EPISODE_ID = "episode-001-adam"
BOOK_ID = 4445
WORK_SOURCE_ID = "SRC-HISTORY-BIDAYAH-ADAM"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def qid(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preview(value: Any, limit: int = 240) -> dict[str, Any]:
    if value is None:
        return {"python_type": "NoneType", "preview": None}
    if isinstance(value, bytes):
        return {
            "python_type": "bytes",
            "byte_length": len(value),
            "hex_prefix": value[:80].hex(),
            "utf8_preview": value[:limit].decode("utf-8", errors="replace"),
        }
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return {
        "python_type": type(value).__name__,
        "char_length": len(text),
        "preview": text[:limit],
    }


def inspect_database(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "MISSING", "path": str(path)}

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        database_list = [
            dict(row)
            for row in connection.execute("PRAGMA database_list").fetchall()
        ]
        integrity = [
            row[0]
            for row in connection.execute("PRAGMA integrity_check").fetchall()
        ]
        encoding = connection.execute("PRAGMA encoding").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]

        objects = connection.execute(
            """
            SELECT type, name, tbl_name, rootpage, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()

        object_reports: list[dict[str, Any]] = []
        long_text_candidates: list[dict[str, Any]] = []

        for obj in objects:
            object_type = str(obj["type"])
            name = str(obj["name"])
            report: dict[str, Any] = {
                "type": object_type,
                "name": name,
                "table_name": obj["tbl_name"],
                "rootpage": obj["rootpage"],
                "create_sql": obj["sql"],
            }

            if object_type not in {"table", "view"}:
                object_reports.append(report)
                continue

            columns = [
                {
                    "cid": row[0],
                    "name": str(row[1]),
                    "declared_type": str(row[2] or ""),
                    "not_null": bool(row[3]),
                    "default": row[4],
                    "primary_key": bool(row[5]),
                }
                for row in connection.execute(
                    f"PRAGMA table_info({qid(name)})"
                ).fetchall()
            ]
            report["columns"] = columns

            try:
                report["row_count"] = connection.execute(
                    f"SELECT COUNT(*) FROM {qid(name)}"
                ).fetchone()[0]
            except sqlite3.DatabaseError as exc:
                report["row_count_error"] = repr(exc)
                object_reports.append(report)
                continue

            column_profiles: list[dict[str, Any]] = []
            for column in columns:
                col = column["name"]
                profile: dict[str, Any] = {
                    "name": col,
                    "declared_type": column["declared_type"],
                }
                try:
                    stats = connection.execute(
                        f"""
                        SELECT
                            COUNT(*) AS total_rows,
                            SUM(CASE WHEN {qid(col)} IS NULL THEN 1 ELSE 0 END) AS null_rows,
                            MAX(LENGTH({qid(col)})) AS max_length,
                            AVG(LENGTH({qid(col)})) AS avg_length
                        FROM {qid(name)}
                        """
                    ).fetchone()
                    profile.update(
                        {
                            "total_rows": stats["total_rows"],
                            "null_rows": stats["null_rows"],
                            "non_null_rows": (
                                stats["total_rows"] - stats["null_rows"]
                            ),
                            "max_length": stats["max_length"],
                            "avg_length": stats["avg_length"],
                        }
                    )

                    samples = connection.execute(
                        f"""
                        SELECT {qid(col)}
                        FROM {qid(name)}
                        WHERE {qid(col)} IS NOT NULL
                        ORDER BY LENGTH({qid(col)}) DESC
                        LIMIT 5
                        """
                    ).fetchall()
                    profile["largest_value_samples"] = [
                        preview(row[0]) for row in samples
                    ]

                    max_length = stats["max_length"] or 0
                    if max_length >= 100:
                        long_text_candidates.append(
                            {
                                "object": name,
                                "column": col,
                                "declared_type": column["declared_type"],
                                "max_length": max_length,
                                "avg_length": stats["avg_length"],
                                "sample": (
                                    preview(samples[0][0])
                                    if samples
                                    else None
                                ),
                            }
                        )
                except sqlite3.DatabaseError as exc:
                    profile["inspection_error"] = repr(exc)

                column_profiles.append(profile)

            report["column_profiles"] = column_profiles

            try:
                sample_rows = connection.execute(
                    f"SELECT rowid AS __rowid__, * FROM {qid(name)} LIMIT 5"
                ).fetchall()
                report["sample_rows"] = [
                    {
                        key: preview(row[key])
                        for key in row.keys()
                    }
                    for row in sample_rows
                ]
            except sqlite3.DatabaseError as exc:
                report["sample_rows_error"] = repr(exc)

            object_reports.append(report)

        return {
            "status": "PASS",
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "encoding": encoding,
            "user_version": user_version,
            "application_id": application_id,
            "database_list": database_list,
            "integrity_check": integrity,
            "objects": object_reports,
            "long_text_candidates": sorted(
                long_text_candidates,
                key=lambda item: (
                    item["max_length"],
                    str(item["object"]),
                    str(item["column"]),
                ),
                reverse=True,
            ),
        }
    finally:
        connection.close()


def find_master_book_rows(master_path: Path, book_id: int) -> dict[str, Any]:
    if not master_path.is_file():
        return {"status": "MISSING", "path": str(master_path)}

    connection = sqlite3.connect(str(master_path))
    connection.row_factory = sqlite3.Row
    try:
        tables = [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]
        hits: list[dict[str, Any]] = []
        for table in tables:
            columns = [
                str(row[1])
                for row in connection.execute(
                    f"PRAGMA table_info({qid(table)})"
                ).fetchall()
            ]
            candidates = [
                col
                for col in columns
                if col.lower() in {
                    "id", "book_id", "bookid", "bkid", "book",
                }
            ]
            for candidate in candidates:
                try:
                    rows = connection.execute(
                        f"SELECT * FROM {qid(table)} "
                        f"WHERE CAST({qid(candidate)} AS TEXT) = ? LIMIT 20",
                        (str(book_id),),
                    ).fetchall()
                except sqlite3.DatabaseError:
                    continue
                for row in rows:
                    hits.append(
                        {
                            "table": table,
                            "matched_column": candidate,
                            "row": {
                                key: preview(row[key], limit=500)
                                for key in row.keys()
                            },
                        }
                    )
        return {
            "status": "PASS",
            "path": str(master_path),
            "size_bytes": master_path.stat().st_size,
            "sha256": sha256_file(master_path),
            "book_id": book_id,
            "matching_rows": hits,
        }
    finally:
        connection.close()


def discover_related_files(
    roots: list[Path],
    book_id: int,
    limit: int = 250,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    needle = str(book_id)
    seen: set[str] = set()

    for root in roots:
        if not root.exists():
            continue
        try:
            iterator = root.rglob(f"*{needle}*")
            for path in iterator:
                if len(results) >= limit:
                    break
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                item: dict[str, Any] = {
                    "path": str(path),
                    "is_file": path.is_file(),
                    "is_dir": path.is_dir(),
                }
                if path.is_file():
                    try:
                        item["size_bytes"] = path.stat().st_size
                    except OSError as exc:
                        item["stat_error"] = repr(exc)
                results.append(item)
        except OSError as exc:
            results.append(
                {
                    "root": str(root),
                    "scan_error": repr(exc),
                }
            )

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument(
        "--master-db",
        default=r"C:\shamela4\database\master.db",
    )
    parser.add_argument(
        "--shamela-root",
        default=r"C:\shamela4",
    )
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / "episode-001-adam"
    secondary = project / "sources" / "secondary"
    materialization_path = secondary / "raw-asset-materialization-v1.json"

    materialization = json.loads(
        materialization_path.read_text(encoding="utf-8-sig")
    )
    matching_assets = [
        asset
        for asset in materialization.get("assets", [])
        if int(asset.get("selected_book_id", -1)) == BOOK_ID
    ]
    if len(matching_assets) != 1:
        raise SystemExit(
            f"EXPECTED_ONE_BOOK_4445_ASSET:actual={len(matching_assets)}"
        )

    asset = matching_assets[0]
    raw_path = project / asset["project_asset_path"]
    master_path = Path(args.master_db)
    shamela_root = Path(args.shamela_root)

    report = {
        "schema_version": "siraj-shamela-book-storage-diagnostic-v1",
        "created_at": now_utc(),
        "episode_id": EPISODE_ID,
        "work_source_id": WORK_SOURCE_ID,
        "book_id": BOOK_ID,
        "materialization_asset": asset,
        "raw_database": inspect_database(raw_path),
        "master_database_book_rows": find_master_book_rows(
            master_path,
            BOOK_ID,
        ),
        "related_files": discover_related_files(
            [
                shamela_root,
                raw_path.parent,
                Path(str(asset.get("source_path", ""))).parent
                if asset.get("source_path")
                else raw_path.parent,
            ],
            BOOK_ID,
        ),
        "interpretation_gate": {
            "status": "HUMAN_REVIEW_REQUIRED",
            "questions": [
                "Which table or file contains the actual Arabic page body?",
                "Is the selected database a metadata/index shard rather than a text asset?",
                "Does master.db point to an alternate content file or storage provider?",
                "Is any long binary value compressed content requiring a documented decoder?",
            ],
        },
    }

    diagnostics = secondary / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    output_path = diagnostics / "shamela-book-4445-diagnostic-v1.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    raw = report["raw_database"]
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output_path),
                "raw_database": {
                    "path": raw.get("path"),
                    "size_bytes": raw.get("size_bytes"),
                    "integrity_check": raw.get("integrity_check"),
                    "objects": [
                        {
                            "type": obj.get("type"),
                            "name": obj.get("name"),
                            "row_count": obj.get("row_count"),
                            "columns": [
                                col["name"]
                                for col in obj.get("columns", [])
                            ],
                        }
                        for obj in raw.get("objects", [])
                    ],
                    "long_text_candidates": raw.get(
                        "long_text_candidates",
                        [],
                    )[:20],
                },
                "master_matching_rows": len(
                    report["master_database_book_rows"].get(
                        "matching_rows",
                        [],
                    )
                ),
                "related_files_found": len(report["related_files"]),
                "next_gate": "BOOK_4445_STORAGE_MAPPING_REVIEW",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
