"""Bounded Shamela pilot-corpus staging and existing-ingestion integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.application.operations_common import CANONICAL_TIMESTAMP, integrity_hash
from src.application.project_ingestion_runtime import ingest_project
from src.application.project_runtime import add_source

from .adapter import ADAPTER_VERSION, ShamelaLocalSourceAdapter


PILOT_BOOKS: tuple[dict[str, Any], ...] = (
    {"book_id": 619, "role": "BIOGRAPHY", "expected_category": "السيرة النبوية"},
    {"book_id": 400, "role": "GENERAL_HISTORY", "expected_category": "التاريخ"},
    {"book_id": 5, "role": "BIOGRAPHY_AND_TRANSMITTERS", "expected_category": "التراجم والطبقات"},
    {"book_id": 151020, "role": "SECTS_AND_TREATISES", "expected_category": "الفرق والردود"},
    {"book_id": 405, "role": "GEOGRAPHY_AND_LINEAGE", "expected_category": "البلدان والرحلات"},
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _architecture_note() -> str:
    return """# Shamela Local Source Adapter Vertical Slice

## Scope

This adapter reads the installed Shamela corpus only. SQLite connections use
`mode=ro&immutable=1`; Lucene access uses `DirectoryReader` only through the
bundled Java runtime. The adapter never creates Lucene indexes, writes locks,
runs repairs or migrations, or writes under the Shamela installation.

## Data boundary

`master.db` supplies catalog metadata. Each selected per-book SQLite database
supplies page, volume, and title structure. The page and title Lucene indexes
supply stored body and footnote fields. Body and footnote segments remain
separate in the staged schema.

## Integration boundary

The staged body file is registered through `project_runtime.add_source` and
processed by `project_ingestion_runtime.ingest_project`. No parallel Siraj
ingestion pipeline is introduced. Source provenance, source type, rights
status, stable locator, database hash, and installation fingerprint are carried
in the existing source registry and ingestion payload metadata.

## Locator contract

Each segment locator contains the installation fingerprint, book identifier,
volume, page or segment fallback, database SHA-256, and segment identifier.
It is deterministic and can be verified against the same local installation.

## Limits

This is a five-book bounded pilot. It does not perform claim/entity/event
extraction, corpus-wide import, graph construction, internet access, or source
side mutations. Rights remain `RIGHTS_UNVERIFIED` pending a separate policy
review.
"""


def build_pilot_corpus(
    adapter: ShamelaLocalSourceAdapter,
    staging_root: str | Path,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Stage exactly five books and optionally ingest their body artifacts."""

    root = Path(staging_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if root == adapter.installation_root or adapter.installation_root in root.parents:
        raise ValueError("STAGING_ROOT_MUST_BE_OUTSIDE_SHAMELA")

    catalog: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    selected_source_ids: set[str] = set()

    for selection in PILOT_BOOKS:
        book_id = int(selection["book_id"])
        staged = adapter.stage_book(book_id, root)
        metadata = adapter.read_metadata(book_id)
        entry = {
            **selection,
            "title": metadata["title"],
            "author": metadata["author"],
            "category": metadata["category"],
            **staged,
        }
        catalog.append(entry)
        validation.append({"book_id": book_id, **staged["validation"]})

        if project_root is not None:
            body_path = root / staged["body_artifact"]
            provenance = {
                "adapter_version": ADAPTER_VERSION,
                "installation_fingerprint": metadata["installation_fingerprint"],
                "database_sha256": metadata["database_sha256"],
                "book_id": book_id,
                "category": metadata["category"],
                "author": metadata["author"],
                "staged_book_artifact": staged["book_artifact"],
            }
            registration = add_source(
                str(project_root),
                str(body_path),
                title=metadata["title"],
                language="ar",
                classification="INTERNAL",
                source_type="SHAMELA_LOCAL_BOOK",
                rights_status="RIGHTS_UNVERIFIED",
                source_locator=staged["source_locator"],
                provenance=provenance,
            )
            source = registration["source"]
            selected_source_ids.add(source["source_id"])
            ledger.append(
                {
                    "book_id": book_id,
                    "source_id": source["source_id"],
                    "source_type": source["source_type"],
                    "source_locator": source["source_locator"],
                    "content_hash": staged["content_hash"],
                    "rights_status": source["rights_status"],
                    "ingestion_status": "PENDING",
                }
            )

    ingestion: dict[str, Any] | None = None
    if project_root is not None:
        ingestion = ingest_project(
            str(project_root),
            source_ids=selected_source_ids,
            working_name="shamela-pilot-ingestion",
        )
        accepted_ids = set(ingestion.get("accepted_source_ids", []))
        for entry in ledger:
            entry["ingestion_status"] = (
                "ACCEPTED" if entry["source_id"] in accepted_ids else "REJECTED"
            )

    catalog = sorted(catalog, key=lambda item: item["book_id"])
    ledger = sorted(ledger, key=lambda item: item["book_id"])
    validation = sorted(validation, key=lambda item: item["book_id"])
    all_valid = len(catalog) == len(PILOT_BOOKS) and all(item["status"] == "VALID" for item in validation)
    manifest = {
        "schema_version": "shamela-pilot-import-manifest-v1",
        "adapter_version": ADAPTER_VERSION,
        "created_at": CANONICAL_TIMESTAMP,
        "installation_fingerprint": adapter.locator_proposal["installation_fingerprint"],
        "book_count": len(catalog),
        "books": catalog,
        "ingestion": ingestion,
        "manifest_hash": integrity_hash(catalog),
    }
    validation_report = {
        "schema_version": "shamela-pilot-validation-v1",
        "adapter_version": ADAPTER_VERSION,
        "created_at": CANONICAL_TIMESTAMP,
        "status": "VALID" if all_valid else "INVALID",
        "expected_book_count": len(PILOT_BOOKS),
        "actual_book_count": len(catalog),
        "book_validations": validation,
        "ingestion_statuses": ledger,
    }
    _atomic_write(root / "shamela-pilot-catalog.json", _canonical_json(catalog))
    _atomic_write(root / "shamela-pilot-import-manifest.json", _canonical_json(manifest))
    _atomic_write(root / "shamela-pilot-source-ledger.json", _canonical_json(ledger))
    _atomic_write(root / "shamela-pilot-validation-report.json", _canonical_json(validation_report))
    _atomic_write(root / "shamela-adapter-architecture.md", _architecture_note())
    return {
        "status": validation_report["status"],
        "staging_root": str(root),
        "catalog": catalog,
        "ledger": ledger,
        "validation": validation_report,
        "ingestion": ingestion,
    }


__all__ = ["PILOT_BOOKS", "build_pilot_corpus"]
