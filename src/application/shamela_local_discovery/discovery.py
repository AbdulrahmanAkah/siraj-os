from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Iterable, Iterator, Mapping, Sequence

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id


DISCOVERY_SCHEMA_VERSION = "shamela-local-discovery-v1"
MAX_PUBLIC_EXCERPT = 180
SQLITE_MAGIC = b"SQLite format 3\x00"
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
DBF_MAGIC = {0x02, 0x03, 0x04, 0x30, 0x31, 0x32, 0x43, 0x63, 0x83, 0x8B, 0xCB, 0xF5}
FIELD_NAMES = {
    "book_key", "date", "author", "group", "book", "id", "page", "parent",
    "body", "m_body", "n_body", "foot", "m_foot", "n_foot", "group_order",
}


class DiscoverySafetyError(ValueError):
    """Raised when a requested discovery operation could mutate source data."""


@dataclass(frozen=True)
class SourceStat:
    size: int
    modified_ns: int


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _source_snapshot(paths: Iterable[Path]) -> dict[str, SourceStat]:
    result: dict[str, SourceStat] = {}
    for path in sorted({item.resolve() for item in paths}, key=lambda item: str(item).casefold()):
        if path.is_file():
            stat = path.stat()
            result[str(path)] = SourceStat(stat.st_size, stat.st_mtime_ns)
    return result


def _bounded_excerpt(value: object, limit: int = MAX_PUBLIC_EXCERPT) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return normalized[:limit]


def sanitize_public_path(path: str | Path, user_profile: str | Path | None = None) -> str:
    """Redact user-profile detail while retaining an operator-useful path."""

    value = str(path)
    profile = Path(user_profile or Path.home()).resolve()
    try:
        resolved = Path(value).resolve()
        if _is_relative_to(resolved, profile):
            suffix = resolved.relative_to(profile)
            return str(Path("%USERPROFILE%") / suffix)
    except (OSError, ValueError):
        pass
    return value


def classify_storage(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if not source.is_file():
        return {"kind": "DIRECTORY" if source.is_dir() else "MISSING", "confidence": "HIGH"}
    with source.open("rb") as stream:
        header = stream.read(64)
    suffix = source.suffix.casefold()
    if header.startswith(SQLITE_MAGIC):
        return {"kind": "SQLITE", "confidence": "HIGH", "magic": "SQLite format 3"}
    if header.startswith(OLE_MAGIC):
        role = "ACCESS_MDB_OR_LEGACY_OLE" if suffix in {".mdb", ".accdb"} else "OLE_COMPOUND_FILE"
        return {"kind": role, "confidence": "HIGH", "magic": header[:8].hex().upper()}
    if any(header.startswith(magic) for magic in ZIP_MAGIC):
        return {"kind": "ZIP_OR_OPENXML_ARCHIVE", "confidence": "HIGH", "magic": header[:4].hex().upper()}
    if header and header[0] in DBF_MAGIC and suffix in {".dbf", ".db"}:
        return {"kind": "DBF", "confidence": "MEDIUM", "magic": f"{header[0]:02X}"}
    if suffix in {".cfs", ".fdt", ".fdx", ".fnm", ".tim", ".tip", ".doc", ".pos", ".dvd", ".dvm", ".si"}:
        return {"kind": "LUCENE_INDEX_COMPONENT", "confidence": "HIGH", "magic": header[:8].hex().upper()}
    if suffix == ".iso":
        return {"kind": "OPTICAL_DISC_IMAGE", "confidence": "MEDIUM", "magic": header[:8].hex().upper()}
    try:
        header.decode("utf-8")
        return {"kind": "PLAIN_TEXT_OR_STRUCTURED_TEXT", "confidence": "LOW", "magic": header[:8].hex().upper()}
    except UnicodeDecodeError:
        return {"kind": "BINARY_OR_PROPRIETARY", "confidence": "LOW", "magic": header[:8].hex().upper()}


def discover_candidates(
    search_roots: Iterable[str | Path],
    *,
    max_depth: int = 4,
    max_entries: int = 100_000,
) -> list[dict[str, object]]:
    """Find Shamela-named candidates with deterministic bounded traversal."""

    indicators = ("shamela", "الشاملة", "المكتبة الشاملة")
    candidates: dict[str, dict[str, object]] = {}
    visited = 0
    for raw_root in sorted({Path(item).resolve() for item in search_roots}, key=lambda item: str(item).casefold()):
        if not raw_root.exists():
            continue
        root_depth = len(raw_root.parts)
        for current, directories, files in os.walk(raw_root, topdown=True, followlinks=False):
            directories[:] = sorted(directories, key=str.casefold)
            files.sort(key=str.casefold)
            current_path = Path(current)
            if len(current_path.parts) - root_depth >= max_depth:
                directories[:] = []
            for name in [current_path.name, *files]:
                visited += 1
                if visited > max_entries:
                    break
                lowered = name.casefold()
                if not any(indicator.casefold() in lowered for indicator in indicators):
                    continue
                candidate = current_path if name == current_path.name else current_path / name
                resolved = candidate.resolve()
                candidates[str(resolved).casefold()] = {
                    "path": str(resolved),
                    "is_directory": resolved.is_dir(),
                    "indicator": name,
                }
            if visited > max_entries:
                break
    return [candidates[key] for key in sorted(candidates)]


@contextmanager
def _open_sqlite_read_only(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        yield connection
    finally:
        connection.close()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sqlite_schema(path: Path, *, include_counts: bool = True) -> dict[str, object]:
    with _open_sqlite_read_only(path) as connection:
        encoding = connection.execute("PRAGMA encoding").fetchone()[0]
        tables = []
        rows = connection.execute(
            "SELECT name,type FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        for name, kind in rows:
            quoted = _quote_identifier(name)
            columns = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
            row_count = None
            if include_counts:
                try:
                    row_count = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
                except sqlite3.DatabaseError:
                    row_count = None
            tables.append(
                {
                    "name": name,
                    "type": kind,
                    "row_count": row_count,
                    "columns": [
                        {"name": column[1], "type": column[2], "primary_key": bool(column[5])}
                        for column in columns
                    ],
                }
            )
    return {"path": str(path), "encoding": encoding, "tables": tables}


def _directory_inventory(root: Path) -> dict[str, object]:
    files = sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: str(item).casefold())
    extensions: Counter[str] = Counter()
    extension_bytes: Counter[str] = Counter()
    total_size = 0
    timestamps = []
    for path in files:
        stat = path.stat()
        extension = path.suffix.casefold() or "<none>"
        extensions[extension] += 1
        extension_bytes[extension] += stat.st_size
        total_size += stat.st_size
        timestamps.append(stat.st_mtime_ns)
    extension_summary = [
        {"extension": extension, "count": extensions[extension], "bytes": extension_bytes[extension]}
        for extension in sorted(extensions)
    ]
    return {
        "path": str(root),
        "file_count": len(files),
        "directory_count": sum(1 for item in root.rglob("*") if item.is_dir()),
        "total_size_bytes": total_size,
        "extensions": extension_summary,
        "earliest_modified_ns": min(timestamps) if timestamps else None,
        "latest_modified_ns": max(timestamps) if timestamps else None,
    }


def _candidate_report(path: Path, installation_root: Path) -> dict[str, object]:
    if path.is_dir():
        inventory = _directory_inventory(path)
        names = {item.name.casefold() for item in path.iterdir()}
        has_books = path == installation_root or "database" in names
        role = "SHAMELA_INSTALLATION" if has_books else "SHAMELA_SUPPORT_DIRECTORY"
        confidence = "HIGH" if has_books else "MEDIUM"
        return {**inventory, "probable_role": role, "confidence": confidence, "contains_books": has_books}
    storage = classify_storage(path)
    stat = path.stat()
    suffix = path.suffix.casefold()
    if suffix == ".iso":
        role, confidence = "INSTALLER_OR_ARCHIVE", "HIGH"
    elif suffix == ".lnk":
        role, confidence = "INSTALLATION_SHORTCUT", "HIGH"
    elif suffix in {".exe", ".msi"}:
        role, confidence = "EXECUTABLE_OR_INSTALLER", "HIGH"
    elif suffix in {".doc", ".docx", ".pdf", ".txt"}:
        role, confidence = "LIKELY_FALSE_POSITIVE_DOCUMENT", "LOW"
    else:
        role, confidence = "UNCLASSIFIED_NAME_MATCH", "LOW"
    return {
        "path": str(path),
        "file_count": 1,
        "total_size_bytes": stat.st_size,
        "extensions": [{"extension": path.suffix.casefold() or "<none>", "count": 1, "bytes": stat.st_size}],
        "modified_ns": stat.st_mtime_ns,
        "probable_role": role,
        "confidence": confidence,
        "contains_books": False,
        "storage": storage,
    }


def _lucene_fields(index_root: Path) -> list[str]:
    discovered: set[str] = set()
    pattern = re.compile(rb"[A-Za-z_][A-Za-z0-9_./:-]{1,80}")
    for path in sorted(index_root.glob("*.fnm"), key=lambda item: item.name.casefold()):
        for match in pattern.finditer(path.read_bytes()):
            value = match.group().decode("ascii", "ignore")
            if value in FIELD_NAMES:
                discovered.add(value)
    return sorted(discovered)


def _sample_book(master_path: Path, book_path: Path, excerpt: str, title_excerpt: str) -> dict[str, object]:
    book_id = int(book_path.stem)
    with _open_sqlite_read_only(master_path) as master:
        metadata = master.execute(
            "SELECT bk.book_id,bk.book_name,c.category_name,a.author_name,bk.meta_data "
            "FROM book bk LEFT JOIN category c ON c.category_id=bk.book_category "
            "LEFT JOIN author a ON a.author_id=bk.main_author WHERE bk.book_id=?",
            (book_id,),
        ).fetchone()
    if metadata is None:
        raise ValueError(f"book {book_id} is missing from master.db")
    with _open_sqlite_read_only(book_path) as book:
        page_stats = book.execute(
            "SELECT COUNT(*),COUNT(DISTINCT part),MIN(part),MAX(part),MIN(page),MAX(page) FROM page"
        ).fetchone()
        title_count = book.execute("SELECT COUNT(*) FROM title").fetchone()[0]
        first_page = book.execute(
            "SELECT id,part,page,number FROM page WHERE page IS NOT NULL ORDER BY id LIMIT 1"
        ).fetchone()
        encoding = book.execute("PRAGMA encoding").fetchone()[0]
    return {
        "book_id": book_id,
        "title": metadata[1],
        "author": metadata[3],
        "category": metadata[2],
        "metadata_excerpt": _bounded_excerpt(metadata[4]),
        "book_database": str(book_path),
        "book_database_sha256": _sha256_file(book_path),
        "page_or_segment_count": page_stats[0],
        "distinct_volume_values": page_stats[1],
        "volume_min": page_stats[2],
        "volume_max": page_stats[3],
        "page_min": page_stats[4],
        "page_max": page_stats[5],
        "title_count": title_count,
        "titles_preserved": title_count > 0 and bool(title_excerpt),
        "volume_and_page_preserved": page_stats[1] > 0 and page_stats[4] is not None,
        "text_extractable": bool(excerpt),
        "encoding": encoding,
        "arabic_text_status": "VALID_UTF8" if excerpt and re.search(r"[\u0600-\u06FF]", excerpt) else "UNVERIFIED",
        "first_reopenable_position": {
            "record_id": first_page[0], "volume": first_page[1], "page": first_page[2], "number": first_page[3]
        } if first_page else None,
        "verification_excerpt": _bounded_excerpt(excerpt),
        "title_verification_excerpt": _bounded_excerpt(title_excerpt),
        "excerpt_policy": f"maximum {MAX_PUBLIC_EXCERPT} characters; no full book text emitted",
    }


def build_locator(
    installation_fingerprint: str,
    book_id: int,
    volume: str | int,
    page: int,
    database_fingerprint: str,
) -> str:
    return (
        f"shamela://local/{installation_fingerprint}/book/{book_id}/"
        f"volume/{volume}/page/{page}?database_sha256={database_fingerprint}"
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def generate_discovery_reports(
    *,
    installation_root: str | Path,
    output_root: str | Path,
    candidate_paths: Sequence[str | Path],
    sample_book_id: int,
    page_excerpt: str,
    title_excerpt: str,
) -> dict[str, object]:
    """Generate the bounded discovery report set without mutating Shamela."""

    installation = Path(installation_root).resolve()
    output = Path(output_root).resolve()
    if not installation.is_dir():
        raise FileNotFoundError(installation)
    if _is_relative_to(output, installation):
        raise DiscoverySafetyError("output_root must be outside the Shamela installation")

    database = installation / "database"
    master_path = database / "master.db"
    book_path = database / "book" / f"{sample_book_id % 1000:03d}" / f"{sample_book_id}.db"
    page_index = database / "store" / "page"
    title_index = database / "store" / "title"
    fingerprint_files = [
        master_path,
        book_path,
        max(page_index.glob("segments_*"), key=lambda item: item.name),
        max(title_index.glob("segments_*"), key=lambda item: item.name),
        installation / "shamela.exe",
    ]
    source_snapshot_before = _source_snapshot(fingerprint_files)

    candidates = [
        _candidate_report(Path(path).resolve(), installation)
        for path in sorted({Path(path).resolve() for path in candidate_paths if Path(path).exists()}, key=lambda item: str(item).casefold())
    ]
    installation_inventory = _directory_inventory(installation)
    storage_samples = []
    sample_paths = [
        master_path,
        database / "service" / "S1.db",
        database / "service" / "S2.db",
        database / "cover.db",
        book_path,
        next(iter(sorted(page_index.glob("*.fnm"), key=lambda item: item.name))),
    ]
    for path in sample_paths:
        storage_samples.append(
            {"path": str(path), "size_bytes": path.stat().st_size, **classify_storage(path)}
        )

    schema_report = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "report_id": deterministic_id("shamela_schema_report", [str(installation), sample_book_id]),
        "generated_at": CANONICAL_TIMESTAMP,
        "sqlite": [
            _sqlite_schema(master_path),
            _sqlite_schema(database / "service" / "S1.db"),
            _sqlite_schema(database / "service" / "S2.db"),
            _sqlite_schema(database / "cover.db"),
            _sqlite_schema(book_path),
        ],
        "lucene": {
            "page_index": {"path": str(page_index), "fields": _lucene_fields(page_index)},
            "title_index": {"path": str(title_index), "fields": _lucene_fields(title_index)},
            "role": "central page text, footnotes, titles, and exact-search fields",
        },
    }
    sample_report = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "report_id": deterministic_id("shamela_sample_book_report", sample_book_id),
        "generated_at": CANONICAL_TIMESTAMP,
        **_sample_book(master_path, book_path, page_excerpt, title_excerpt),
    }

    file_fingerprints = [
        {"relative_path": path.relative_to(installation).as_posix(), "size_bytes": path.stat().st_size, "sha256": _sha256_file(path)}
        for path in fingerprint_files
    ]
    installation_fingerprint = sha256(_canonical_json(file_fingerprints).encode("utf-8")).hexdigest()
    first_position = sample_report["first_reopenable_position"] or {"volume": 1, "page": 1}
    locator = build_locator(
        installation_fingerprint,
        sample_book_id,
        first_position["volume"],
        int(first_position["page"]),
        sample_report["book_database_sha256"],
    )
    locator_report = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "report_id": deterministic_id("shamela_locator_proposal", locator),
        "generated_at": CANONICAL_TIMESTAMP,
        "locator": locator,
        "installation_fingerprint": installation_fingerprint,
        "database_fingerprint": sample_report["book_database_sha256"],
        "fingerprint_inputs": file_fingerprints,
        "properties": ["DETERMINISTIC", "REOPENABLE", "LOCAL_COPY_BOUND", "PAGE_ADDRESSABLE"],
    }
    candidate_report = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "report_id": deterministic_id("shamela_candidates", [item["path"] for item in candidates]),
        "generated_at": CANONICAL_TIMESTAMP,
        "probable_installation": str(installation),
        "candidates": candidates,
    }
    inventory_report = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "report_id": deterministic_id("shamela_storage_inventory", installation_fingerprint),
        "generated_at": CANONICAL_TIMESTAMP,
        "installation": installation_inventory,
        "storage_samples": storage_samples,
        "storage_conclusion": {
            "book_metadata": "SQLite master.db",
            "book_structure": "one SQLite database per book",
            "page_and_title_text": "Lucene 10.x indexes",
            "search_indexes": "Lucene component files",
            "support_data": "SQLite service databases and binary blobs",
        },
        "sampling_policy": "hash only selected identity files; do not hash all 8,000+ book databases",
    }
    recommendation_text = """# Shamela Local Discovery Recommendation

## Recommendation

Use a dedicated read-only adapter for the discovered hybrid layout:

1. Open `master.db` and per-book databases with SQLite URI `mode=ro&immutable=1`.
2. Read page and title text through the bundled-compatible Lucene reader.
3. Bind every locator to the installation fingerprint and selected book database SHA-256.
4. Prefer a staging copy for future ingestion jobs, but only after an explicit user action; discovery itself must remain direct read-only.

## Why

- SQLite contains reliable book, author, category, page, volume, and title relationships.
- Lucene contains the actual `body` and `foot` text plus title text.
- An application export may be useful as a fallback, but it is less deterministic and may update application state.
- No Shamela file needs to be modified to build the future adapter.

## Boundary

This report does not implement `ShamelaLocalSourceAdapter`, import a book, create a corpus, or start a knowledge graph.
"""
    discovery_report = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "report_id": deterministic_id("shamela_discovery", [installation_fingerprint, sample_book_id]),
        "generated_at": CANONICAL_TIMESTAMP,
        "status": "DISCOVERY_COMPLETE",
        "installation": str(installation),
        "storage_type": "HYBRID_SQLITE_AND_LUCENE",
        "text_available": sample_report["text_extractable"],
        "volume_available": sample_report["distinct_volume_values"] > 0,
        "page_available": sample_report["page_min"] is not None,
        "sample_book_id": sample_book_id,
        "sample_book_title": sample_report["title"],
        "recommended_integration": "READ_ONLY_SQLITE_PLUS_LUCENE_ADAPTER_WITH_OPTIONAL_EXPLICIT_STAGING_FOR_INGESTION",
        "source_mutation": "NONE",
        "full_book_text_emitted": False,
        "public_log_installation": sanitize_public_path(installation),
        "limitations": [
            "Lucene 10.x compatibility must be preserved by the future adapter.",
            "Application service databases contain opaque binary fields not required for the first adapter.",
            "No ingestion or corpus generation was performed.",
        ],
    }

    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "shamela-installation-candidates.json", candidate_report)
    _write_json(output / "shamela-storage-inventory.json", inventory_report)
    _write_json(output / "shamela-schema-report.json", schema_report)
    _write_json(output / "shamela-sample-book-report.json", sample_report)
    _write_json(output / "shamela-locator-proposal.json", locator_report)
    (output / "shamela-integration-recommendation.md").write_text(
        recommendation_text, encoding="utf-8", newline="\n"
    )
    _write_json(output / "shamela-discovery-report.json", discovery_report)

    source_snapshot_after = _source_snapshot(fingerprint_files)
    if source_snapshot_before != source_snapshot_after:
        raise DiscoverySafetyError("a sampled Shamela source timestamp or size changed during discovery")
    return {
        "output_root": str(output),
        "files": sorted(path.name for path in output.iterdir() if path.is_file()),
        "installation_fingerprint": installation_fingerprint,
        "source_snapshot_unchanged": True,
        "sample_book": sample_report,
        "locator": locator,
    }
