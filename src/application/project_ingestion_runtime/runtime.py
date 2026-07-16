from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
)
from src.application.project_runtime import (
    load_project,
    load_sources,
    project_paths,
    verify_project,
)
from src.application.rc_hardening import (
    SQLiteConnectionConfig,
    SQLitePersistenceAdapter,
)
from src.application.source_ingestion_architecture.models import (
    IngestionBatch,
    IngestionUnit,
    SourceIngestionPlan,
)
from src.application.source_ingestion_architecture.source_ingestion_architect import (
    SourceIngestionArchitect,
)
from src.application.source_ingestion_runtime.models import IngestionPayload
from src.application.source_ingestion_runtime.source_ingestion_executor import (
    SourceIngestionExecutor,
)


INGESTION_SCHEMA_VERSION = "siraj-project-ingestion-v1"

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".csv",
    ".html",
    ".htm",
    ".xml",
    ".yaml",
    ".yml",
}

_MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".json": "application/json",
    ".csv": "text/csv",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}


class ProjectSourceIngestionArchitect(SourceIngestionArchitect):
    """Structural adapter for already-registered local project sources."""

    def __init__(self) -> None:
        # Deliberately avoid SourceIngestionArchitect's discovery-planner
        # constructor requirement. Project sources have already been acquired.
        self.source_acquisition_planner = None
        self._plans_by_id = {}

    def validate_ingestion_plan(
        self,
        plan: SourceIngestionPlan,
        source_acquisition_plan=None,
    ) -> bool:
        if not isinstance(plan, SourceIngestionPlan):
            return False

        if not plan.plan_id or not plan.source_acquisition_plan_id:
            return False

        if not plan.batches:
            return False

        units = [
            unit
            for batch in plan.batches
            for unit in batch.units
        ]

        if plan.unit_count != len(units):
            return False

        unit_ids = [unit.unit_id for unit in units]
        target_ids = [unit.acquisition_target_id for unit in units]

        if len(unit_ids) != len(set(unit_ids)):
            return False

        if len(target_ids) != len(set(target_ids)):
            return False

        if not any(unit.validation_level == "STRICT" for unit in units):
            return False

        for batch in plan.batches:
            if not batch.batch_id or not batch.units:
                return False

            if [unit.position for unit in batch.units] != list(
                range(len(batch.units))
            ):
                return False

            for unit in batch.units:
                if unit.normalization_strategy != "DOCUMENT_NORMALIZATION":
                    return False
                if unit.fingerprint_strategy != "SHA256_FINGERPRINT":
                    return False
                if unit.deduplication_policy != "STRICT_DEDUPLICATION":
                    return False
                if unit.validation_level != "STRICT":
                    return False

        return True


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


def _atomic_write(path: Path, data: bytes) -> None:
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


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write(path, _canonical_json(payload).encode("utf-8"))


def _decode_text(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1256"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise ValueError("UNSUPPORTED_TEXT_ENCODING")


def inspect_source(
    project_root: str,
    source_id: str,
) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    registry = load_sources(root)

    source = next(
        (
            item
            for item in registry["sources"]
            if item.get("source_id") == source_id
        ),
        None,
    )

    if source is None:
        raise FileNotFoundError(f"SOURCE_ID_NOT_FOUND:{source_id}")

    stored = (root / source["stored_path"]).resolve(strict=False)

    try:
        stored.relative_to(root)
    except ValueError as error:
        raise ValueError("SOURCE_PATH_ESCAPE") from error

    if not stored.is_file():
        raise FileNotFoundError(f"SOURCE_FILE_NOT_FOUND:{stored}")

    data = stored.read_bytes()
    suffix = stored.suffix.lower()
    actual_hash = sha256(data).hexdigest()

    report: dict[str, Any] = {
        "project_id": project["project_id"],
        "source_id": source_id,
        "path": source["stored_path"],
        "suffix": suffix,
        "size_bytes": len(data),
        "sha256": actual_hash,
        "registered_sha256": source.get("sha256"),
        "hash_valid": actual_hash == source.get("sha256"),
        "supported_for_ingestion": suffix in _TEXT_EXTENSIONS,
        "media_type": _MEDIA_TYPES.get(
            suffix,
            "application/octet-stream",
        ),
    }

    if suffix in _TEXT_EXTENSIONS:
        text, encoding = _decode_text(data)
        report.update(
            {
                "encoding": encoding,
                "character_count": len(text),
                "line_count": len(text.splitlines()),
                "empty": not bool(text.strip()),
            }
        )

    return report


def build_project_ingestion_plan(
    project_root: str,
) -> SourceIngestionPlan:
    project = load_project(project_root)
    registry = load_sources(project_root)

    units: list[IngestionUnit] = []

    for position, source in enumerate(
        sorted(
            registry["sources"],
            key=lambda item: item["source_id"],
        )
    ):
        source_id = source["source_id"]

        units.append(
            IngestionUnit(
                unit_id=deterministic_id(
                    "ingestion_unit",
                    [
                        project["project_id"],
                        source_id,
                        "DOCUMENT_NORMALIZATION",
                        "SHA256_FINGERPRINT",
                        "STRICT_DEDUPLICATION",
                        "STRICT",
                    ],
                ),
                acquisition_target_id=source_id,
                normalization_strategy="DOCUMENT_NORMALIZATION",
                fingerprint_strategy="SHA256_FINGERPRINT",
                deduplication_policy="STRICT_DEDUPLICATION",
                validation_level="STRICT",
                position=position,
            )
        )

    if not units:
        raise ValueError("NO_SOURCES_REGISTERED")

    batch_id = deterministic_id(
        "ingestion_batch",
        [
            project["project_id"],
            [unit.unit_id for unit in units],
        ],
    )

    batch = IngestionBatch(
        batch_id=batch_id,
        acquisition_batch_id=deterministic_id(
            "project_source_batch",
            [project["project_id"]],
        ),
        units=units,
    )

    return SourceIngestionPlan(
        plan_id=deterministic_id(
            "source_ingestion_plan",
            [project["project_id"], batch_id],
        ),
        source_acquisition_plan_id=deterministic_id(
            "project_acquisition_plan",
            [project["project_id"]],
        ),
        batches=[batch],
        unit_count=len(units),
    )


def _build_payloads(
    project_root: Path,
    registry: dict[str, Any],
) -> dict[str, IngestionPayload]:
    payloads: dict[str, IngestionPayload] = {}

    for source in sorted(
        registry["sources"],
        key=lambda item: item["source_id"],
    ):
        source_id = source["source_id"]
        stored = (project_root / source["stored_path"]).resolve(strict=False)

        try:
            stored.relative_to(project_root)
        except ValueError as error:
            raise ValueError("SOURCE_PATH_ESCAPE") from error

        if not stored.is_file():
            raise FileNotFoundError(f"SOURCE_FILE_NOT_FOUND:{stored}")

        suffix = stored.suffix.lower()

        if suffix not in _TEXT_EXTENSIONS:
            raise ValueError(
                f"UNSUPPORTED_SOURCE_TYPE:{source_id}:{suffix or 'none'}"
            )

        raw = stored.read_bytes()
        text, encoding = _decode_text(raw)

        if not text.strip():
            raise ValueError(f"EMPTY_SOURCE_CONTENT:{source_id}")

        normalized_text = (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .lstrip("\ufeff")
        )

        payloads[source_id] = IngestionPayload(
            target_id=source_id,
            content_bytes=normalized_text.encode("utf-8"),
            media_type=_MEDIA_TYPES.get(suffix, "text/plain"),
            metadata={
                "source_id": source_id,
                "title": str(source.get("title", "")),
                "language": str(source.get("language", "und")),
                "classification": str(
                    source.get("classification", "INTERNAL")
                ),
                "original_filename": str(
                    source.get("original_filename", "")
                ),
                "stored_path": str(source.get("stored_path", "")),
                "source_encoding": encoding,
                "source_sha256": str(source.get("sha256", "")),
            },
        )

    return payloads


def _serialise_plan(plan: SourceIngestionPlan) -> dict[str, Any]:
    return asdict(plan)


def _serialise_execution(
    result,
    source_ids_by_unit: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": INGESTION_SCHEMA_VERSION,
        "execution_id": result.execution_id,
        "source_ingestion_plan_id": result.source_ingestion_plan_id,
        "processed_count": result.processed_count,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "duplicate_count": result.duplicate_count,
        "validation_results": [
            {
                **asdict(item),
                "source_id": source_ids_by_unit.get(item.unit_id, ""),
            }
            for item in result.validation_results
        ],
        "fingerprints": [
            {
                **asdict(item),
                "source_id": source_ids_by_unit.get(item.unit_id, ""),
            }
            for item in result.fingerprints
        ],
        "deduplication_results": [
            {
                **asdict(item),
                "source_id": source_ids_by_unit.get(item.unit_id, ""),
            }
            for item in result.deduplication_results
        ],
    }


def ingest_project(project_root: str) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")

    verification = verify_project(root)
    if verification.status != "VALID":
        raise ValueError("PROJECT_VERIFICATION_FAILED")

    project = load_project(root)
    registry = load_sources(root)
    paths = project_paths(root)

    plan = build_project_ingestion_plan(root)
    architect = ProjectSourceIngestionArchitect()

    if not architect.validate_ingestion_plan(plan):
        raise ValueError("INVALID_PROJECT_INGESTION_PLAN")

    payloads = _build_payloads(root, registry)
    executor = SourceIngestionExecutor(architect)
    result = executor.execute_ingestion(plan, payloads)

    source_ids_by_unit = {
        unit.unit_id: unit.acquisition_target_id
        for batch in plan.batches
        for unit in batch.units
    }

    working_root = Path(paths.working_root) / "ingestion"
    normalized_root = working_root / "normalized"
    normalized_root.mkdir(parents=True, exist_ok=True)

    normalized_sources: list[dict[str, Any]] = []

    for normalized in result.normalized_payloads:
        source_id = source_ids_by_unit[normalized.unit_id]
        relative_path = Path("normalized") / f"{source_id}.txt"
        output_path = working_root / relative_path

        _atomic_write(output_path, normalized.normalized_bytes)

        normalized_sources.append(
            {
                "source_id": source_id,
                "unit_id": normalized.unit_id,
                "path": relative_path.as_posix(),
                "media_type": normalized.normalized_media_type,
                "metadata": normalized.normalized_metadata,
                "size_bytes": len(normalized.normalized_bytes),
                "sha256": sha256(
                    normalized.normalized_bytes
                ).hexdigest(),
            }
        )

    plan_payload = {
        "schema_version": INGESTION_SCHEMA_VERSION,
        "project_id": project["project_id"],
        "created_at": CANONICAL_TIMESTAMP,
        "plan": _serialise_plan(plan),
    }

    execution_payload = _serialise_execution(
        result,
        source_ids_by_unit,
    )
    execution_payload["project_id"] = project["project_id"]
    execution_payload["created_at"] = CANONICAL_TIMESTAMP

    normalized_payload = {
        "schema_version": INGESTION_SCHEMA_VERSION,
        "project_id": project["project_id"],
        "execution_id": result.execution_id,
        "sources": sorted(
            normalized_sources,
            key=lambda item: item["source_id"],
        ),
    }

    fingerprints_payload = {
        "schema_version": INGESTION_SCHEMA_VERSION,
        "project_id": project["project_id"],
        "execution_id": result.execution_id,
        "fingerprints": execution_payload["fingerprints"],
    }

    _write_json(working_root / "ingestion-plan.json", plan_payload)
    _write_json(
        working_root / "ingestion-result.json",
        execution_payload,
    )
    _write_json(
        working_root / "normalized-sources.json",
        normalized_payload,
    )
    _write_json(
        working_root / "fingerprints.json",
        fingerprints_payload,
    )

    with SQLitePersistenceAdapter(
        SQLiteConnectionConfig(paths.database)
    ) as adapter:
        adapter.initialize()
        transaction = adapter.save_many(
            [
                (
                    "INGESTION_PLAN",
                    plan.plan_id,
                    plan_payload,
                ),
                (
                    "INGESTION_RESULT",
                    result.execution_id,
                    execution_payload,
                ),
                (
                    "NORMALIZED_SOURCE_REGISTRY",
                    result.execution_id,
                    normalized_payload,
                ),
                (
                    "INGESTION_FINGERPRINTS",
                    result.execution_id,
                    fingerprints_payload,
                ),
            ]
        )

    if not transaction.committed:
        raise RuntimeError(
            transaction.error_code or "INGESTION_PERSISTENCE_FAILED"
        )

    status = (
        "VALID"
        if result.rejected_count == 0
        else "INVALID"
    )

    return {
        "project_id": project["project_id"],
        "status": status,
        "execution_id": result.execution_id,
        "plan_id": plan.plan_id,
        "processed_count": result.processed_count,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "duplicate_count": result.duplicate_count,
        "working_root": str(working_root),
        "persistence_record_ids": transaction.record_ids,
    }


def ingestion_status(project_root: str) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    paths = project_paths(root)

    result_path = (
        Path(paths.working_root)
        / "ingestion"
        / "ingestion-result.json"
    )

    if not result_path.is_file():
        return {
            "project_id": project["project_id"],
            "status": "NOT_RUN",
            "result_path": str(result_path),
        }

    try:
        payload = json.loads(
            result_path.read_text(encoding="utf-8-sig")
        )
    except json.JSONDecodeError as error:
        raise ValueError("INVALID_INGESTION_RESULT") from error

    required = {
        "execution_id",
        "processed_count",
        "accepted_count",
        "rejected_count",
        "duplicate_count",
    }

    if not required.issubset(payload):
        raise ValueError("INVALID_INGESTION_RESULT")

    status = (
        "VALID"
        if payload["rejected_count"] == 0
        else "INVALID"
    )

    return {
        "project_id": project["project_id"],
        "status": status,
        "result_path": str(result_path),
        "execution_id": payload["execution_id"],
        "processed_count": payload["processed_count"],
        "accepted_count": payload["accepted_count"],
        "rejected_count": payload["rejected_count"],
        "duplicate_count": payload["duplicate_count"],
    }


__all__ = [
    "INGESTION_SCHEMA_VERSION",
    "ProjectSourceIngestionArchitect",
    "build_project_ingestion_plan",
    "ingest_project",
    "ingestion_status",
    "inspect_source",
]
