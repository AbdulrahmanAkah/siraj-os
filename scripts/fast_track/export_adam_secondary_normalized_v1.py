from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.application.shamela_local_adapter import ShamelaLocalSourceAdapter

EPISODE_ID = "episode-001-adam"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def object_sha256(data: Any) -> str:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            line = json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n"
            stream.write(line)
            digest.update(line.encode("utf-8"))
    return {
        "rows": len(rows),
        "sha256": digest.hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def locate_discovery_root(installation_root: Path) -> Path:
    preferred = Path(
        r"C:\SIRAJ\Workspace\first-project\working\shamela-local-discovery"
    )
    candidates: list[Path] = [preferred]

    siraj_root = Path(r"C:\SIRAJ")
    if siraj_root.is_dir():
        candidates.extend(
            item.parent
            for item in siraj_root.rglob("shamela-discovery-report.json")
        )

    valid: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)

        report_path = candidate / "shamela-discovery-report.json"
        locator_path = candidate / "shamela-locator-proposal.json"
        if not report_path.is_file() or not locator_path.is_file():
            continue

        try:
            report = read_json(report_path)
            reported_installation = Path(str(report["installation"])).resolve()
        except Exception:
            continue

        if reported_installation != installation_root.resolve():
            continue
        if report.get("storage_type") != "HYBRID_SQLITE_AND_LUCENE":
            continue
        valid.append(candidate)

    if not valid:
        raise FileNotFoundError(
            "SHAMELA_DISCOVERY_ROOT_NOT_FOUND_FOR_C_SHAMELA4"
        )

    valid.sort(
        key=lambda path: (
            0 if path == preferred.resolve() else 1,
            len(str(path)),
            str(path).casefold(),
        )
    )
    return valid[0]


def selected_assets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise ValueError("MATERIALIZATION_ASSETS_LIST_REQUIRED")

    result = [
        item
        for item in assets
        if isinstance(item, dict)
        and item.get("work_source_id")
        and item.get("selected_book_id") is not None
    ]
    if len(result) != 9:
        raise ValueError(f"EXPECTED_NINE_SELECTED_ASSETS:actual={len(result)}")
    return sorted(result, key=lambda item: str(item["work_source_id"]))


def export_one(
    project: Path,
    normalized_root: Path,
    adapter: ShamelaLocalSourceAdapter,
    asset: dict[str, Any],
) -> dict[str, Any]:
    source_id = str(asset["work_source_id"])
    book_id = int(asset["selected_book_id"])
    raw_path = project / str(asset["project_asset_path"])

    if not raw_path.is_file():
        raise FileNotFoundError(f"RAW_ASSET_MISSING:{source_id}:{raw_path}")

    copied_sha = file_sha256(raw_path)
    expected_sha = str(asset.get("sha256") or "")
    if expected_sha and copied_sha != expected_sha:
        raise ValueError(
            f"RAW_ASSET_CHECKSUM_MISMATCH:{source_id}:"
            f"expected={expected_sha}:actual={copied_sha}"
        )

    metadata = adapter.read_metadata(book_id)
    live_sha = str(metadata["database_sha256"])
    if live_sha != copied_sha:
        raise ValueError(
            f"LIVE_AND_MATERIALIZED_DB_MISMATCH:{source_id}:"
            f"live={live_sha}:materialized={copied_sha}"
        )

    book = adapter.read_book(book_id)
    validation = adapter.validate_book(book)
    if validation["status"] != "VALID":
        raise ValueError(
            f"ADAPTER_BOOK_VALIDATION_FAILED:{source_id}:{validation}"
        )

    book_root = normalized_root / source_id
    pages_path = book_root / "pages.jsonl"
    toc_path = book_root / "toc.jsonl"

    pages: list[dict[str, Any]] = []
    for sequence, segment in enumerate(book["segments"], start=1):
        row = {
            "schema_version": "siraj-shamela-normalized-page-v2",
            "episode_id": EPISODE_ID,
            "work_source_id": source_id,
            "book_id": book_id,
            "shamela_page_id": int(segment["segment_id"]),
            "sequence_num": sequence,
            "volume": segment.get("volume"),
            "page_num": segment.get("page"),
            "page_label": segment.get("number"),
            "canonical_locator": segment["locator"],
            "content_raw": segment["body_original"],
            "content_text": segment["body_normalized"],
            "footnote_raw": segment.get("foot_original", ""),
            "footnote_text": segment.get("foot_normalized", ""),
            "database_sha256": live_sha,
            "installation_fingerprint": metadata[
                "installation_fingerprint"
            ],
        }
        row["record_sha256"] = object_sha256(row)
        pages.append(row)

    toc: list[dict[str, Any]] = []
    for sequence, heading in enumerate(book["headings"], start=1):
        row = {
            "schema_version": "siraj-shamela-normalized-heading-v2",
            "episode_id": EPISODE_ID,
            "work_source_id": source_id,
            "book_id": book_id,
            "heading_id": int(heading["heading_id"]),
            "sequence_num": sequence,
            "parent_heading_id": heading.get("parent_heading_id"),
            "page_segment_id": heading.get("page_segment_id"),
            "title_raw": heading["text_original"],
            "title_text": heading["text_normalized"],
            "canonical_locator": heading["locator"],
            "database_sha256": live_sha,
            "installation_fingerprint": metadata[
                "installation_fingerprint"
            ],
        }
        row["record_sha256"] = object_sha256(row)
        toc.append(row)

    page_meta = write_jsonl(pages_path, pages)
    toc_meta = write_jsonl(toc_path, toc)
    page_meta["project_path"] = pages_path.relative_to(project).as_posix()
    toc_meta["project_path"] = toc_path.relative_to(project).as_posix()

    manifest = {
        "schema_version": "siraj-secondary-normalized-book-manifest-v2",
        "episode_id": EPISODE_ID,
        "work_source_id": source_id,
        "book_id": book_id,
        "book_title": metadata.get("title") or asset.get("book_title", ""),
        "author": metadata.get("author") or asset.get("author", ""),
        "category": metadata.get("category") or asset.get("category", ""),
        "storage_contract": {
            "type": "HYBRID_SQLITE_AND_LUCENE",
            "catalog_metadata": "database/master.db",
            "page_structure": metadata["database_relative_path"],
            "page_text_index": "database/store/page",
            "title_text_index": "database/store/title",
            "adapter_version": book["adapter_version"],
        },
        "source_integrity": {
            "materialized_database_path": str(
                asset["project_asset_path"]
            ).replace("\\", "/"),
            "materialized_database_sha256": copied_sha,
            "installation_database_sha256": live_sha,
            "installation_fingerprint": metadata[
                "installation_fingerprint"
            ],
            "content_hash": book["content_hash"],
        },
        "normalized_files": {
            "pages": page_meta,
            "toc": toc_meta,
        },
        "validation": {
            **validation,
            "sqlite_page_count": book["page_count"],
            "lucene_nonempty_segment_count": book["segment_count"],
            "skipped_empty_segment_count": len(
                book.get("skipped_empty_segment_ids", [])
            ),
            "skipped_empty_segment_ids_sample": book.get(
                "skipped_empty_segment_ids", []
            )[:25],
            "heading_count": book["heading_count"],
        },
        "permissions": {
            "allowed_for_local_deterministic_search": True,
            "allowed_for_gemini_locator_discovery": False,
            "allowed_for_quotation": False,
            "approved_for_evidence": False,
        },
        "created_at": utc_now(),
    }

    manifest_path = book_root / "manifest.json"
    write_json(manifest_path, manifest)
    manifest["manifest_project_path"] = manifest_path.relative_to(
        project
    ).as_posix()
    manifest["manifest_sha256"] = file_sha256(manifest_path)
    return manifest


def create_test(repo: Path) -> Path:
    path = (
        repo
        / "tests"
        / "integration"
        / "test_adam_secondary_lucene_normalized_export_v2.py"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_adam_secondary_lucene_normalized_export_v2() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    path = (
        project
        / "sources"
        / "secondary"
        / "normalized-export-manifest-v1.json"
    )
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))

    assert manifest["status"] == "PASS_READY_FOR_BOUNDED_LOCAL_SEARCH"
    assert manifest["storage_contract"] == "HYBRID_SQLITE_AND_LUCENE"
    assert manifest["book_count"] == 9
    assert manifest["total_page_records"] > 0
    assert manifest["permissions"]["gemini_execution_enabled"] is False

    for book in manifest["books"]:
        assert book["validation"]["status"] == "VALID"
        assert book["normalized_files"]["pages"]["rows"] > 0
        assert (
            book["source_integrity"]["materialized_database_sha256"]
            == book["source_integrity"]["installation_database_sha256"]
        )
        pages = project / book["normalized_files"]["pages"]["project_path"]
        toc = project / book["normalized_files"]["toc"]["project_path"]
        assert pages.is_file()
        assert toc.is_file()
        assert sha256_file(pages) == book["normalized_files"]["pages"]["sha256"]
        assert sha256_file(toc) == book["normalized_files"]["toc"]["sha256"]
        first = json.loads(
            pages.read_text(encoding="utf-8").splitlines()[0]
        )
        assert first["content_raw"].strip()
        assert first["canonical_locator"].startswith("shamela://local/")
""",
        encoding="utf-8",
        newline="\n",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument(
        "--installation-root",
        default=r"C:\shamela4",
    )
    parser.add_argument(
        "--maximum-pages-per-book",
        type=int,
        default=200_000,
    )
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    secondary = project / "sources" / "secondary"
    materialization_path = (
        secondary / "raw-asset-materialization-v1.json"
    )
    export_plan_path = secondary / "normalized-export-plan-v1.json"

    installation_root = Path(args.installation_root).resolve()
    discovery_root = locate_discovery_root(installation_root)

    adapter = ShamelaLocalSourceAdapter(
        installation_root,
        discovery_root,
        maximum_pages_per_book=args.maximum_pages_per_book,
    )
    assets = selected_assets(read_json(materialization_path))

    normalized_root = secondary / "assets" / "normalized"
    if normalized_root.exists():
        shutil.rmtree(normalized_root)
    normalized_root.mkdir(parents=True, exist_ok=True)
    (normalized_root / ".gitignore").write_text(
        "*/pages.jsonl\n*/toc.jsonl\n",
        encoding="ascii",
        newline="\n",
    )

    books: list[dict[str, Any]] = []
    for asset in assets:
        print(
            json.dumps(
                {
                    "event": "EXPORT_BOOK_START",
                    "work_source_id": asset["work_source_id"],
                    "book_id": asset["selected_book_id"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        book = export_one(project, normalized_root, adapter, asset)
        books.append(book)
        print(
            json.dumps(
                {
                    "event": "EXPORT_BOOK_PASS",
                    "work_source_id": book["work_source_id"],
                    "book_id": book["book_id"],
                    "pages": book["normalized_files"]["pages"]["rows"],
                    "titles": book["normalized_files"]["toc"]["rows"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    total_pages = sum(
        int(item["normalized_files"]["pages"]["rows"])
        for item in books
    )
    total_titles = sum(
        int(item["normalized_files"]["toc"]["rows"])
        for item in books
    )

    global_manifest = {
        "schema_version": "siraj-secondary-normalized-export-manifest-v2",
        "episode_id": EPISODE_ID,
        "status": "PASS_READY_FOR_BOUNDED_LOCAL_SEARCH",
        "storage_contract": "HYBRID_SQLITE_AND_LUCENE",
        "installation_root": str(installation_root),
        "discovery_root": str(discovery_root),
        "installation_fingerprint": adapter.locator_proposal[
            "installation_fingerprint"
        ],
        "book_count": len(books),
        "total_page_records": total_pages,
        "total_toc_records": total_titles,
        "books": books,
        "permissions": {
            "gemini_execution_enabled": False,
            "source_approval_changed": False,
            "quotation_approval_changed": False,
        },
        "next_gate": "DETERMINISTIC_TOPIC_PREFILTER",
        "created_at": utc_now(),
    }
    global_path = secondary / "normalized-export-manifest-v1.json"
    write_json(global_path, global_manifest)

    plan = read_json(export_plan_path)
    plan.update(
        {
            "status": "PASS_NORMALIZED_EXPORT_COMPLETE",
            "storage_contract": "HYBRID_SQLITE_AND_LUCENE",
            "completed_at": utc_now(),
            "normalized_export_manifest": global_path.relative_to(
                project
            ).as_posix(),
            "normalized_book_count": len(books),
            "total_page_records": total_pages,
            "total_toc_records": total_titles,
            "next_gate": "DETERMINISTIC_TOPIC_PREFILTER",
            "gemini_execution_enabled": False,
        }
    )
    write_json(export_plan_path, plan)
    test_path = create_test(repo)

    print(
        json.dumps(
            {
                "status": "PASS",
                "normalized_export_manifest": str(global_path),
                "normalized_root": str(normalized_root),
                "integration_test": str(test_path),
                "storage_contract": "HYBRID_SQLITE_AND_LUCENE",
                "discovery_root": str(discovery_root),
                "counts": {
                    "books": len(books),
                    "pages": total_pages,
                    "titles": total_titles,
                },
                "gemini_execution_enabled": False,
                "source_approval_changed": False,
                "quotation_approval_changed": False,
                "next_gate": "DETERMINISTIC_TOPIC_PREFILTER",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
