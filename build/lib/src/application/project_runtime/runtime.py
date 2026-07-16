from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
)
from src.application.rc_hardening import (
    SQLiteConnectionConfig,
    SQLitePersistenceAdapter,
)


PROJECT_SCHEMA_VERSION = "siraj-project-v1"
SOURCE_REGISTRY_SCHEMA_VERSION = "siraj-source-registry-v1"

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


@dataclass(frozen=True)
class ProjectPaths:
    root: str
    project_manifest: str
    source_registry: str
    database: str
    sources_root: str
    exports_root: str
    working_root: str
    manifests_root: str


@dataclass(frozen=True)
class ProjectVerificationIssue:
    code: str
    detail: str = ""
    subject_id: str = ""


@dataclass(frozen=True)
class ProjectVerificationReport:
    project_id: str
    status: str
    source_count: int
    verified_source_count: int
    issues: list[ProjectVerificationIssue]


def _absolute_path(raw: str | Path, field_name: str) -> Path:
    path = Path(raw).expanduser()

    if not path.is_absolute():
        raise ValueError(f"{field_name}_MUST_BE_ABSOLUTE")

    return path.resolve(strict=False)


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path}")

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"INVALID_JSON:{path}:{error.lineno}:{error.colno}"
        ) from error


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary: str | None = None

    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".siraj-",
            suffix=".tmp",
            delete=False,
        )
        temporary = handle.name

        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_bytes(path, _canonical_json(payload).encode("utf-8"))


def project_paths(project_root: str | Path) -> ProjectPaths:
    root = _absolute_path(project_root, "PROJECT_ROOT")

    return ProjectPaths(
        root=str(root),
        project_manifest=str(root / "project.json"),
        source_registry=str(root / "sources.json"),
        database=str(root / "siraj.sqlite"),
        sources_root=str(root / "sources" / "raw"),
        exports_root=str(root / "exports"),
        working_root=str(root / "working"),
        manifests_root=str(root / "manifests"),
    )


def load_project(project_root: str | Path) -> dict[str, Any]:
    paths = project_paths(project_root)
    manifest = _read_json(Path(paths.project_manifest))

    if manifest.get("schema_version") != PROJECT_SCHEMA_VERSION:
        raise ValueError("INVALID_PROJECT_SCHEMA")

    project_id = manifest.get("project_id")

    if not isinstance(project_id, str) or not project_id:
        raise ValueError("INVALID_PROJECT_ID")

    return manifest


def load_sources(project_root: str | Path) -> dict[str, Any]:
    paths = project_paths(project_root)
    registry = _read_json(Path(paths.source_registry))

    if registry.get("schema_version") != SOURCE_REGISTRY_SCHEMA_VERSION:
        raise ValueError("INVALID_SOURCE_REGISTRY_SCHEMA")

    if not isinstance(registry.get("sources"), list):
        raise ValueError("INVALID_SOURCE_REGISTRY")

    return registry


def initialize_project(
    project_root: str,
    slug: str,
    topic: str,
    *,
    language: str = "ar",
) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    slug = slug.strip().lower()
    topic = topic.strip()
    language = language.strip().lower()

    if not _SLUG_PATTERN.fullmatch(slug):
        raise ValueError("INVALID_PROJECT_SLUG")

    if not topic:
        raise ValueError("PROJECT_TOPIC_REQUIRED")

    if not language:
        raise ValueError("PROJECT_LANGUAGE_REQUIRED")

    paths = project_paths(root)
    manifest_path = Path(paths.project_manifest)
    registry_path = Path(paths.source_registry)
    database_path = Path(paths.database)

    if manifest_path.exists() or registry_path.exists() or database_path.exists():
        raise ValueError("PROJECT_ALREADY_INITIALIZED")

    for directory in (
        root,
        Path(paths.sources_root),
        Path(paths.exports_root),
        Path(paths.working_root),
        Path(paths.manifests_root),
    ):
        directory.mkdir(parents=True, exist_ok=True)

    project_id = deterministic_id(
        "project",
        [slug, topic, language, PROJECT_SCHEMA_VERSION],
    )

    manifest = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project_id": project_id,
        "slug": slug,
        "topic": topic,
        "language": language,
        "created_at": CANONICAL_TIMESTAMP,
        "state": "INITIALIZED",
        "paths": {
            "database": "siraj.sqlite",
            "sources": "sources/raw",
            "exports": "exports",
            "working": "working",
            "manifests": "manifests",
        },
    }

    registry = {
        "schema_version": SOURCE_REGISTRY_SCHEMA_VERSION,
        "project_id": project_id,
        "sources": [],
    }

    _atomic_write_json(manifest_path, manifest)
    _atomic_write_json(registry_path, registry)

    with SQLitePersistenceAdapter(
        SQLiteConnectionConfig(str(database_path))
    ) as adapter:
        schema = adapter.initialize()
        transaction = adapter.persist_repository(project_id, manifest)

    if not transaction.committed:
        raise RuntimeError(
            transaction.error_code or "PROJECT_PERSISTENCE_FAILED"
        )

    return {
        "project": manifest,
        "paths": asdict(paths),
        "database_schema": asdict(schema),
        "persistence_record_ids": transaction.record_ids,
    }


def add_source(
    project_root: str,
    source_path: str,
    *,
    title: str | None = None,
    language: str = "und",
    classification: str = "INTERNAL",
) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    source = _absolute_path(source_path, "SOURCE_PATH")

    if not source.is_file():
        raise FileNotFoundError(f"SOURCE_NOT_FOUND:{source}")

    project = load_project(root)
    registry = load_sources(root)
    paths = project_paths(root)

    data = source.read_bytes()

    if not data:
        raise ValueError("EMPTY_SOURCE_FILE")

    digest = sha256(data).hexdigest()

    for existing in registry["sources"]:
        if existing.get("sha256") == digest:
            return {
                "source": existing,
                "duplicate": True,
                "added": False,
            }

    suffix = source.suffix.lower()
    source_id = deterministic_id(
        "source",
        [project["project_id"], digest],
    )

    stored_name = f"{source_id}{suffix}"
    stored_path = Path(paths.sources_root) / stored_name

    _atomic_write_bytes(stored_path, data)

    source_record = {
        "source_id": source_id,
        "title": (title or source.stem).strip(),
        "language": language.strip().lower() or "und",
        "classification": classification.strip().upper() or "INTERNAL",
        "original_filename": source.name,
        "stored_path": stored_path.relative_to(root).as_posix(),
        "media_type": suffix.removeprefix(".") or "unknown",
        "size_bytes": len(data),
        "sha256": digest,
        "created_at": CANONICAL_TIMESTAMP,
    }

    with SQLitePersistenceAdapter(
        SQLiteConnectionConfig(paths.database)
    ) as adapter:
        adapter.initialize()
        transaction = adapter.save(
            "SOURCE",
            source_id,
            source_record,
        )

    if not transaction.committed:
        stored_path.unlink(missing_ok=True)
        raise RuntimeError(
            transaction.error_code or "SOURCE_PERSISTENCE_FAILED"
        )

    source_record["persistence_record_id"] = transaction.record_ids[0]

    registry["sources"].append(source_record)
    registry["sources"] = sorted(
        registry["sources"],
        key=lambda item: item["source_id"],
    )

    _atomic_write_json(Path(paths.source_registry), registry)

    return {
        "source": source_record,
        "duplicate": False,
        "added": True,
    }


def list_sources(project_root: str) -> dict[str, Any]:
    project = load_project(project_root)
    registry = load_sources(project_root)

    return {
        "project_id": project["project_id"],
        "source_count": len(registry["sources"]),
        "sources": sorted(
            registry["sources"],
            key=lambda item: item["source_id"],
        ),
    }


def verify_project(project_root: str) -> ProjectVerificationReport:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    issues: list[ProjectVerificationIssue] = []

    try:
        project = load_project(root)
    except (FileNotFoundError, ValueError) as error:
        return ProjectVerificationReport(
            project_id="",
            status="INVALID",
            source_count=0,
            verified_source_count=0,
            issues=[
                ProjectVerificationIssue(
                    "INVALID_PROJECT_MANIFEST",
                    str(error),
                )
            ],
        )

    project_id = project["project_id"]
    paths = project_paths(root)

    try:
        registry = load_sources(root)
    except (FileNotFoundError, ValueError) as error:
        return ProjectVerificationReport(
            project_id=project_id,
            status="INVALID",
            source_count=0,
            verified_source_count=0,
            issues=[
                ProjectVerificationIssue(
                    "INVALID_SOURCE_REGISTRY",
                    str(error),
                    project_id,
                )
            ],
        )

    if registry.get("project_id") != project_id:
        issues.append(
            ProjectVerificationIssue(
                "PROJECT_ID_MISMATCH",
                "sources.json belongs to another project",
                project_id,
            )
        )

    database_path = Path(paths.database)

    if not database_path.is_file():
        issues.append(
            ProjectVerificationIssue(
                "DATABASE_NOT_FOUND",
                str(database_path),
                project_id,
            )
        )
    else:
        try:
            with SQLitePersistenceAdapter(
                SQLiteConnectionConfig(
                    str(database_path),
                    read_only=True,
                )
            ) as adapter:
                adapter.initialize()
        except Exception as error:
            issues.append(
                ProjectVerificationIssue(
                    "DATABASE_VERIFICATION_FAILED",
                    f"{type(error).__name__}:{error}",
                    project_id,
                )
            )

    source_ids: set[str] = set()
    source_hashes: set[str] = set()
    verified_count = 0

    for source in registry["sources"]:
        source_id = str(source.get("source_id", ""))
        expected_hash = str(source.get("sha256", ""))
        relative_path = str(source.get("stored_path", ""))

        if not source_id:
            issues.append(
                ProjectVerificationIssue(
                    "MISSING_SOURCE_ID",
                    relative_path,
                )
            )
            continue

        if source_id in source_ids:
            issues.append(
                ProjectVerificationIssue(
                    "DUPLICATE_SOURCE_ID",
                    source_id,
                    source_id,
                )
            )
        source_ids.add(source_id)

        if expected_hash in source_hashes:
            issues.append(
                ProjectVerificationIssue(
                    "DUPLICATE_SOURCE_HASH",
                    expected_hash,
                    source_id,
                )
            )
        source_hashes.add(expected_hash)

        candidate = (root / relative_path).resolve(strict=False)

        try:
            candidate.relative_to(root)
        except ValueError:
            issues.append(
                ProjectVerificationIssue(
                    "SOURCE_PATH_ESCAPE",
                    relative_path,
                    source_id,
                )
            )
            continue

        if not candidate.is_file():
            issues.append(
                ProjectVerificationIssue(
                    "SOURCE_FILE_NOT_FOUND",
                    relative_path,
                    source_id,
                )
            )
            continue

        actual_data = candidate.read_bytes()
        actual_hash = sha256(actual_data).hexdigest()

        if actual_hash != expected_hash:
            issues.append(
                ProjectVerificationIssue(
                    "SOURCE_HASH_MISMATCH",
                    relative_path,
                    source_id,
                )
            )
            continue

        if len(actual_data) != source.get("size_bytes"):
            issues.append(
                ProjectVerificationIssue(
                    "SOURCE_SIZE_MISMATCH",
                    relative_path,
                    source_id,
                )
            )
            continue

        verified_count += 1

    status = "VALID" if not issues else "INVALID"

    return ProjectVerificationReport(
        project_id=project_id,
        status=status,
        source_count=len(registry["sources"]),
        verified_source_count=verified_count,
        issues=issues,
    )


__all__ = [
    "PROJECT_SCHEMA_VERSION",
    "SOURCE_REGISTRY_SCHEMA_VERSION",
    "ProjectPaths",
    "ProjectVerificationIssue",
    "ProjectVerificationReport",
    "add_source",
    "initialize_project",
    "list_sources",
    "load_project",
    "load_sources",
    "project_paths",
    "verify_project",
]
