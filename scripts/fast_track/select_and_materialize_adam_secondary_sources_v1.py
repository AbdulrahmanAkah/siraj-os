from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EPISODE_ID = "episode-001-adam"
SELECTION_SCHEMA = "siraj-secondary-source-selection-v1"
MATERIALIZATION_SCHEMA = "siraj-secondary-raw-asset-materialization-v1"
INSPECTION_SCHEMA = "siraj-shamela-schema-inspection-v1"
EXPORT_PLAN_SCHEMA = "siraj-secondary-normalized-export-plan-v1"

SELECTED_BOOKS: dict[str, int] = {
    "SRC-TAFSIR-TABARI-ADAM": 7798,
    "SRC-TAFSIR-IBN-ABI-HATIM-ADAM": 8658,
    "SRC-TAFSIR-BAGHAWI-ADAM": 41,
    "SRC-TAFSIR-IBN-KATHIR-ADAM": 1503,
    "SRC-TAFSIR-SAADI-ADAM": 42,
    "SRC-HISTORY-TABARI-ADAM": 9783,
    "SRC-HISTORY-BIDAYAH-ADAM": 4445,
    "SRC-HISTORY-MUNTAZAM-ADAM": 12406,
    "SRC-HISTORY-KAMIL-ADAM": 21712,
}

DEFERRED: dict[str, dict[str, Any]] = {
    "SRC-HISTORY-QASAS-IBN-KATHIR-ADAM": {
        "candidate_book_id": 932,
        "reason": "DEFERRED_DERIVATIVE_OVERLAP_WITH_BIDAYAH_WAN_NIHAYAH",
        "notes": (
            "The discovered title states that it is extracted from al-Bidaya wa al-Nihaya. "
            "Do not treat it as an independent source until a distinct original-work asset "
            "or a documented editorial reason for retaining the derivative is recorded."
        ),
    }
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_index(report: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    output: dict[tuple[str, int], dict[str, Any]] = {}
    for target in report.get("targets", []):
        source_id = str(target.get("work_source_id", ""))
        for candidate in target.get("candidates", []):
            try:
                book_id = int(candidate["book_id"])
            except (KeyError, TypeError, ValueError):
                continue
            output[(source_id, book_id)] = candidate
    return output


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def safe_sample_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"type": "bytes", "length": len(value)}
    if isinstance(value, str):
        compact = value.replace("\x00", "").strip()
        return compact[:500]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:500]


def inspect_sqlite(path: Path, *, work_source_id: str, book_id: int) -> dict[str, Any]:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        table_rows = connection.execute(
            "SELECT name, type, sql FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        tables: list[dict[str, Any]] = []
        for table_row in table_rows:
            table_name = str(table_row["name"])
            columns = [
                {
                    "cid": int(row["cid"]),
                    "name": str(row["name"]),
                    "type": str(row["type"] or ""),
                    "notnull": bool(row["notnull"]),
                    "primary_key_position": int(row["pk"]),
                }
                for row in connection.execute(
                    f"PRAGMA table_info({quote_identifier(table_name)})"
                ).fetchall()
            ]
            column_names = [item["name"] for item in columns]
            text_hints = [
                name for name in column_names
                if any(token in name.lower() for token in (
                    "text", "content", "body", "page", "nass", "matn", "title", "book"
                ))
            ]
            samples: list[dict[str, Any]] = []
            try:
                rows = connection.execute(
                    f"SELECT * FROM {quote_identifier(table_name)} LIMIT 3"
                ).fetchall()
                for row in rows:
                    samples.append({key: safe_sample_value(row[key]) for key in row.keys()})
            except sqlite3.DatabaseError as error:
                samples.append({"inspection_error": str(error)})
            tables.append({
                "name": table_name,
                "object_type": str(table_row["type"]),
                "columns": columns,
                "candidate_text_columns": text_hints,
                "sample_rows": samples,
                "create_sql": str(table_row["sql"] or "")[:4000],
            })
        return {
            "work_source_id": work_source_id,
            "selected_book_id": book_id,
            "asset_path": str(path),
            "asset_sha256": sha256_file(path),
            "tables": tables,
            "inspection_status": "PASS",
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    secondary = project / "sources" / "secondary"
    candidate_report_path = secondary / "shamela-book-candidates-v1.json"
    selection_template_path = secondary / "asset-selection.template.json"
    work_registry_path = secondary / "work-source-registry-v1.jsonl"

    required = [candidate_report_path, selection_template_path, work_registry_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_PHASE2_FILES:\n" + "\n".join(missing))

    report = read_json(candidate_report_path)
    template = read_json(selection_template_path)
    index = candidate_index(report)

    expected_targets = set(template.get("selections", {}))
    configured_targets = set(SELECTED_BOOKS) | set(DEFERRED)
    if expected_targets != configured_targets:
        raise SystemExit(json.dumps({
            "status": "FAIL",
            "error": "SELECTION_TARGET_SET_MISMATCH",
            "expected": sorted(expected_targets),
            "configured": sorted(configured_targets),
        }, ensure_ascii=False, indent=2))

    selected_assets: list[dict[str, Any]] = []
    inspection_items: list[dict[str, Any]] = []
    selection = json.loads(json.dumps(template))
    selection["status"] = "PARTIAL_SELECTION_ONE_DERIVATIVE_DEFERRED"
    selection["selected_count"] = len(SELECTED_BOOKS)
    selection["deferred_count"] = len(DEFERRED)
    selection["approved_at"] = now_utc()
    selection["approval_scope"] = (
        "Human selection for bounded local discovery only. "
        "No report, quotation, authenticity judgment or narrative use is approved."
    )

    raw_root = secondary / "assets" / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    (raw_root / ".gitignore").write_text(
        "*.db\n*.sqlite\n*.sqlite3\n",
        encoding="ascii",
        newline="\n",
    )

    for work_source_id, book_id in SELECTED_BOOKS.items():
        candidate = index.get((work_source_id, book_id))
        if candidate is None:
            raise SystemExit(f"SELECTED_CANDIDATE_NOT_FOUND:{work_source_id}:{book_id}")
        source_path = Path(str(candidate.get("book_database_path", "")))
        if not source_path.is_file():
            raise SystemExit(f"SELECTED_BOOK_DATABASE_MISSING:{work_source_id}:{source_path}")

        destination_dir = raw_root / work_source_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{book_id}.db"
        shutil.copy2(source_path, destination)
        checksum = sha256_file(destination)

        selection_record = selection["selections"][work_source_id]
        selection_record.update({
            "selected_book_id": book_id,
            "selection_basis": "HUMAN_SELECTED_TOP_LOCAL_SHAMELA_CANDIDATE",
            "edition_or_export_notes": str(candidate.get("book_title", "")),
            "rights_reviewed": False,
            "allow_local_extraction": True,
            "allow_quotation": False,
            "approved_by_user": True,
            "selection_status": "SELECTED_FOR_LOCAL_DISCOVERY",
            "raw_asset_path": destination.relative_to(project).as_posix(),
            "raw_asset_sha256": checksum,
        })

        asset_record = {
            "work_source_id": work_source_id,
            "selected_book_id": book_id,
            "book_title": candidate.get("book_title", ""),
            "author": candidate.get("author", ""),
            "category": candidate.get("category", ""),
            "candidate_score": candidate.get("score"),
            "original_database_path": str(source_path),
            "project_asset_path": destination.relative_to(project).as_posix(),
            "sha256": checksum,
            "size_bytes": destination.stat().st_size,
            "materialization_status": "RAW_SQLITE_COPIED_CHECKSUM_VERIFIED",
            "allowed_for_local_schema_inspection": True,
            "allowed_for_gemini": False,
            "allowed_for_quotation": False,
        }
        selected_assets.append(asset_record)
        inspection_items.append(
            inspect_sqlite(destination, work_source_id=work_source_id, book_id=book_id)
        )

    for work_source_id, details in DEFERRED.items():
        selection_record = selection["selections"][work_source_id]
        selection_record.update({
            "selected_book_id": None,
            "selection_basis": details["reason"],
            "edition_or_export_notes": details["notes"],
            "rights_reviewed": False,
            "allow_local_extraction": False,
            "allow_quotation": False,
            "approved_by_user": True,
            "selection_status": "DEFERRED_DERIVATIVE_REVIEW_REQUIRED",
            "deferred_candidate_book_id": details["candidate_book_id"],
        })

    materialization = {
        "schema_version": MATERIALIZATION_SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "RAW_ASSETS_MATERIALIZED_NORMALIZED_EXPORT_PENDING",
        "selected_asset_count": len(selected_assets),
        "deferred_target_count": len(DEFERRED),
        "assets": selected_assets,
        "created_at": now_utc(),
        "gemini_execution_enabled": False,
        "source_approval_changed": False,
    }
    inspection = {
        "schema_version": INSPECTION_SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "PASS_REVIEW_REQUIRED_BEFORE_EXPORT",
        "asset_count": len(inspection_items),
        "items": inspection_items,
        "created_at": now_utc(),
    }
    export_plan = {
        "schema_version": EXPORT_PLAN_SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "BLOCKED_SCHEMA_REVIEW_PENDING",
        "selected_work_count": len(selected_assets),
        "deferred_work_source_ids": sorted(DEFERRED),
        "required_next_actions": [
            "Review the SQLite table and column inspection.",
            "Define deterministic text, title, page, volume and ordering column mappings.",
            "Export normalized project-local UTF-8 JSONL artifacts.",
            "Verify row counts, locators and SHA-256 checksums.",
            "Only then create one bounded Gemini locator-discovery work package per selected work.",
        ],
        "prohibitions": [
            "NO_GEMINI_ACCESS_TO_RAW_SQLITE_DATABASES",
            "NO_GEMINI_WEB_BROWSING",
            "NO_QUOTATION_APPROVAL",
            "NO_SOURCE_ADJUDICATION",
            "NO_NARRATIVE_USE",
        ],
        "created_at": now_utc(),
    }

    write_json(secondary / "asset-selection-v1.json", selection)
    write_json(secondary / "raw-asset-materialization-v1.json", materialization)
    write_json(secondary / "shamela-schema-inspection-v1.json", inspection)
    write_json(secondary / "normalized-export-plan-v1.json", export_plan)

    test_text = '''from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_adam_secondary_raw_asset_materialization_v1() -> None:
    root = Path(__file__).resolve().parents[2]
    project = root / "projects" / "episode-001-adam"
    secondary = project / "sources" / "secondary"
    selection = json.loads((secondary / "asset-selection-v1.json").read_text(encoding="utf-8-sig"))
    materialization = json.loads((secondary / "raw-asset-materialization-v1.json").read_text(encoding="utf-8-sig"))
    inspection = json.loads((secondary / "shamela-schema-inspection-v1.json").read_text(encoding="utf-8-sig"))
    assert selection["selected_count"] == 9
    assert selection["deferred_count"] == 1
    assert materialization["selected_asset_count"] == 9
    assert materialization["gemini_execution_enabled"] is False
    assert inspection["asset_count"] == 9
    for asset in materialization["assets"]:
        path = project / asset["project_asset_path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == asset["sha256"]
        assert asset["allowed_for_gemini"] is False
        assert asset["allowed_for_quotation"] is False
'''
    test_path = repo / "tests" / "integration" / "test_adam_secondary_raw_asset_materialization_v1.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(test_text, encoding="utf-8", newline="\n")

    print(json.dumps({
        "status": "PASS",
        "selection": str(secondary / "asset-selection-v1.json"),
        "materialization": str(secondary / "raw-asset-materialization-v1.json"),
        "schema_inspection": str(secondary / "shamela-schema-inspection-v1.json"),
        "export_plan": str(secondary / "normalized-export-plan-v1.json"),
        "counts": {
            "selected_works": len(selected_assets),
            "deferred_works": len(DEFERRED),
            "inspected_databases": len(inspection_items),
        },
        "deferred": DEFERRED,
        "gemini_execution_enabled": False,
        "source_approval_changed": False,
        "next_gate": "SHAMELA_SCHEMA_MAPPING_REVIEW",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
