from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import platform
import sys
from typing import Any

from src.application.project_research_planning_runtime import (
    build_research_plan,
    get_research_task,
    list_research_tasks,
    research_status,
    verify_research_plan,
)

from src.application.project_assessment_runtime import (
    assess_project_claims,
    assessment_status,
    list_contradictions,
    list_gaps,
    verify_assessment,
)

from src.application.project_knowledge_runtime import (
    extract_project_knowledge,
    knowledge_status,
    list_claims,
    list_evidence,
    verify_knowledge,
)

from src.application.project_ingestion_runtime import (
    ingest_project,
    ingestion_status,
    inspect_source,
)

from src.application.project_runtime import (
    add_source,
    initialize_project,
    list_sources,
    project_paths,
    verify_project,
)
from src.application.shamela_local_adapter import (
    ShamelaLocalSourceAdapter,
    build_pilot_corpus,
)
from src.application.shamela_historical_extraction import (
    run_shamela_historical_extraction,
)
from src.application.shamela_extraction_quality_audit import (
    GoldAnnotationStore,
    GoldAnnotationValidationError,
    build_local_workbench_server,
)

from src.application.rc_hardening import (
    ExportFailure,
    ExportOverwritePolicy,
    ExportPathPolicy,
    FileExportAdapter,
    RendererDryRunAdapter,
    SQLiteConnectionConfig,
    SQLitePersistenceAdapter,
    SQLiteSchemaIdentity,
)
from src.application.local_video_production import (
    build_render as build_local_render,
    build_storyboard as build_local_storyboard,
    build_subtitles as build_local_subtitles,
    initialize_production as initialize_local_production,
    verify_render as verify_local_render,
    build_documentary_v2_render,
    build_documentary_v2_storyboard,
    build_documentary_v2_subtitles,
    initialize_documentary_v2,
    verify_documentary_v2_render,
    DocumentaryV3Config,
    build_documentary_v3_assets,
    build_documentary_v3_render,
    build_documentary_v3_subtitles,
    initialize_documentary_v3,
    verify_documentary_v3_render,
)

VERSION = "0.1.0"

EXIT_CODES = {
    "SUCCESS": 0,
    "INVALID_INPUT": 2,
    "CONFIGURATION_FAILURE": 3,
    "POLICY_DENIAL": 4,
    "DEPENDENCY_FAILURE": 5,
    "EXECUTION_FAILURE": 6,
    "VALIDATION_FAILURE": 7,
    "BLOCKED": 8,
    "INTERNAL_ERROR": 9,
}


def _normalise(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _normalise(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {
            str(key): _normalise(value[key])
            for key in sorted(value, key=str)
        }
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _result(
    command: str,
    status: str,
    *,
    data: Any = None,
    error: str | None = None,
    exit_code: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": command,
        "status": status,
        "trace_id": "cli-v2-local",
        "version": VERSION,
    }

    if data is not None:
        payload["data"] = _normalise(data)

    if error is not None:
        payload["error"] = error

    payload["exit_code"] = (
        EXIT_CODES.get(status, EXIT_CODES["INTERNAL_ERROR"])
        if exit_code is None
        else exit_code
    )
    return payload


def _format(payload: dict[str, Any], as_json: bool) -> str:
    if as_json:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )

    command = payload["command"]
    status = payload["status"]

    if "error" in payload:
        return f"{command}: {status} ({payload['error']})"

    if "data" in payload:
        return (
            f"{command}: {status}\n"
            + json.dumps(
                payload["data"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )

    return f"{command}: {status}"


def _absolute_path(raw: str, field: str) -> Path:
    path = Path(raw).expanduser()

    if not path.is_absolute():
        raise ValueError(f"{field}_MUST_BE_ABSOLUTE")

    return path.resolve(strict=False)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path}")

    try:
        # utf-8-sig accepts ordinary UTF-8 and PowerShell UTF-8 files with BOM.
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"INVALID_JSON:{path}:{error.lineno}:{error.colno}"
        ) from error


def _database_adapter(
    database: str,
    *,
    read_only: bool = False,
    schema_version: str = "rc-hardening-v1",
) -> SQLitePersistenceAdapter:
    path = _absolute_path(database, "DATABASE_PATH")

    return SQLitePersistenceAdapter(
        SQLiteConnectionConfig(
            database_path=str(path),
            read_only=read_only,
        ),
        SQLiteSchemaIdentity(schema_version=schema_version),
    )


def command_version() -> dict[str, Any]:
    return _result(
        "version",
        "SUCCESS",
        data={
            "version": VERSION,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    )


def command_health() -> dict[str, Any]:
    python_supported = (
        sys.version_info.major == 3
        and sys.version_info.minor == 13
    )
    platform_supported = sys.platform == "win32"

    status = (
        "SUCCESS"
        if python_supported and platform_supported
        else "DEPENDENCY_FAILURE"
    )

    return _result(
        "health",
        status,
        data={
            "python_supported": python_supported,
            "platform_supported": platform_supported,
            "python": platform.python_version(),
            "platform": sys.platform,
        },
        error=None if status == "SUCCESS" else "UNSUPPORTED_RUNTIME",
    )


def command_config_show() -> dict[str, Any]:
    return _result(
        "config-show",
        "SUCCESS",
        data={
            "runtime": {
                "mode": "LOCAL",
                "network_default": "DENY",
                "subprocess_default": "DENY",
            },
            "persistence": {
                "backend": "SQLITE",
                "schema_version": "rc-hardening-v1",
            },
            "render": {
                "mode": "DRY_RUN_ONLY",
            },
            "release": {
                "version": VERSION,
                "supported_os": ["Windows"],
                "supported_python": ["3.13"],
            },
        },
    )


def command_config_validate() -> dict[str, Any]:
    problems: list[str] = []

    if sys.platform != "win32":
        problems.append("UNSUPPORTED_PLATFORM")

    if not (
        sys.version_info.major == 3
        and sys.version_info.minor == 13
    ):
        problems.append("UNSUPPORTED_PYTHON")

    return _result(
        "config-validate",
        "SUCCESS" if not problems else "VALIDATION_FAILURE",
        data={"issues": problems},
        error=None if not problems else "INVALID_RUNTIME_CONFIGURATION",
    )


def command_persistence_init(database: str) -> dict[str, Any]:
    path = _absolute_path(database, "DATABASE_PATH")

    with _database_adapter(str(path)) as adapter:
        schema = adapter.initialize()

    return _result(
        "persistence-init",
        "SUCCESS",
        data={
            "database": str(path),
            "database_exists": path.is_file(),
            "schema": schema,
        },
    )


def command_persistence_verify(
    database: str,
    schema_version: str,
) -> dict[str, Any]:
    path = _absolute_path(database, "DATABASE_PATH")

    if not path.is_file():
        return _result(
            "persistence-verify",
            "DEPENDENCY_FAILURE",
            error="DATABASE_NOT_FOUND",
        )

    with _database_adapter(
        str(path),
        read_only=True,
        schema_version=schema_version,
    ) as adapter:
        schema = adapter.initialize()
        row = adapter._db().execute(
            "SELECT COUNT(*) AS total FROM persisted_records"
        ).fetchone()

    return _result(
        "persistence-verify",
        "SUCCESS",
        data={
            "database": str(path),
            "schema": schema,
            "record_count": int(row["total"]),
        },
    )


def command_persistence_snapshot(
    database: str,
    snapshot_id: str,
    input_path: str,
) -> dict[str, Any]:
    source = _absolute_path(input_path, "INPUT_PATH")
    payload = _read_json(source)

    with _database_adapter(database) as adapter:
        adapter.initialize()
        transaction = adapter.persist_snapshot(snapshot_id, payload)

    if not transaction.committed:
        return _result(
            "persistence-snapshot",
            "EXECUTION_FAILURE",
            data=transaction,
            error=transaction.error_code or "SNAPSHOT_FAILED",
        )

    return _result(
        "persistence-snapshot",
        "SUCCESS",
        data=transaction,
    )


def command_persistence_restore(
    database: str,
    record_id: str,
) -> dict[str, Any]:
    path = _absolute_path(database, "DATABASE_PATH")

    if not path.is_file():
        return _result(
            "persistence-restore",
            "DEPENDENCY_FAILURE",
            error="DATABASE_NOT_FOUND",
        )

    with _database_adapter(str(path), read_only=True) as adapter:
        adapter.initialize()
        recovery = adapter.restore(record_id)

    if recovery.status != "VALID":
        return _result(
            "persistence-restore",
            "VALIDATION_FAILURE",
            data=recovery,
            error=(
                recovery.issues[0].code
                if recovery.issues
                else "RESTORE_FAILED"
            ),
        )

    return _result(
        "persistence-restore",
        "SUCCESS",
        data=recovery,
    )


def command_migration(
    database: str,
    target_version: str,
    *,
    apply: bool,
    current_version: str,
) -> dict[str, Any]:
    path = _absolute_path(database, "DATABASE_PATH")

    if not path.is_file():
        return _result(
            "migration-apply" if apply else "migration-plan",
            "DEPENDENCY_FAILURE",
            error="DATABASE_NOT_FOUND",
        )

    with _database_adapter(
        str(path),
        schema_version=current_version,
    ) as adapter:
        adapter.initialize()
        migration = adapter.migrate_schema(
            target_version,
            dry_run=not apply,
        )

    return _result(
        "migration-apply" if apply else "migration-plan",
        "SUCCESS",
        data=migration,
    )


def _export_one(
    exporter: FileExportAdapter,
    descriptor: dict[str, Any],
):
    relative_path = descriptor.get("path")
    artifact_type = descriptor.get("type")
    content = descriptor.get("content")

    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("EXPORT_PATH_REQUIRED")

    if artifact_type == "json":
        return exporter.export_json(relative_path, content)

    if artifact_type == "markdown":
        if not isinstance(content, str):
            raise ValueError("MARKDOWN_CONTENT_MUST_BE_STRING")
        return exporter.export_markdown(relative_path, content)

    raise ValueError(f"UNSUPPORTED_EXPORT_TYPE:{artifact_type}")


def command_export_build(
    input_path: str,
    output_root: str,
    replace: bool,
) -> dict[str, Any]:
    package_path = _absolute_path(input_path, "INPUT_PATH")
    output = _absolute_path(output_root, "OUTPUT_ROOT")
    package = _read_json(package_path)

    if not isinstance(package, dict):
        raise ValueError("EXPORT_PACKAGE_MUST_BE_OBJECT")

    descriptors = package.get("artifacts")

    if not isinstance(descriptors, list) or not descriptors:
        raise ValueError("EXPORT_ARTIFACTS_REQUIRED")

    exporter = FileExportAdapter(
        ExportPathPolicy(str(output)),
        ExportOverwritePolicy("REPLACE" if replace else "DENY"),
    )

    artifacts = [_export_one(exporter, item) for item in descriptors]

    subtitles = package.get("subtitles")
    if subtitles is not None:
        if not isinstance(subtitles, list):
            raise ValueError("SUBTITLES_MUST_BE_LIST")
        artifacts.append(exporter.export_srt(subtitles))
        artifacts.append(exporter.export_webvtt(subtitles))

    credits = package.get("credits")
    if credits is not None:
        if not isinstance(credits, list):
            raise ValueError("CREDITS_MUST_BE_LIST")
        artifacts.append(exporter.export_credits(credits))

    sources = package.get("sources")
    if sources is not None:
        if not isinstance(sources, list):
            raise ValueError("SOURCES_MUST_BE_LIST")
        artifacts.append(exporter.export_source_appendix(sources))

    report = exporter.build_manifest(
        artifacts,
        package.get("limitations", []),
    )

    status = "SUCCESS" if report.status == "VALID" else "EXECUTION_FAILURE"

    return _result(
        "export-build",
        status,
        data=report,
        error=None if status == "SUCCESS" else "EXPORT_FAILED",
    )


def command_render_dry_run(
    manifest_path: str,
    asset_root: str,
) -> dict[str, Any]:
    manifest_file = _absolute_path(manifest_path, "MANIFEST_PATH")
    root = _absolute_path(asset_root, "ASSET_ROOT")
    manifest = _read_json(manifest_file)

    report = RendererDryRunAdapter(str(root)).dry_run(manifest)

    status_map = {
        "VALID": "SUCCESS",
        "BLOCKED": "BLOCKED",
        "INVALID": "VALIDATION_FAILURE",
    }
    status = status_map.get(report.status, "INTERNAL_ERROR")

    return _result(
        "render-dry-run",
        status,
        data=report,
        error=None if status == "SUCCESS" else report.status,
    )







def command_project_plan_research(
    project_root: str,
) -> dict[str, Any]:
    result = build_research_plan(project_root)

    return _result(
        "project-plan-research",
        "SUCCESS",
        data=result,
    )


def command_research_status(
    project_root: str,
) -> dict[str, Any]:
    result = research_status(project_root)

    status = (
        "SUCCESS"
        if result["status"] == "PLANNED"
        else "BLOCKED"
        if result["status"] == "NOT_RUN"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "research-status",
        status,
        data=result,
        error=None if status == "SUCCESS" else result["status"],
    )


def command_research_tasks(
    project_root: str,
) -> dict[str, Any]:
    return _result(
        "research-tasks",
        "SUCCESS",
        data=list_research_tasks(project_root),
    )


def command_research_task_show(
    project_root: str,
    task_id: str,
) -> dict[str, Any]:
    return _result(
        "research-task-show",
        "SUCCESS",
        data=get_research_task(
            project_root,
            task_id,
        ),
    )


def command_research_verify(
    project_root: str,
) -> dict[str, Any]:
    report = verify_research_plan(project_root)

    status = (
        "SUCCESS"
        if report.status == "VALID"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "research-verify",
        status,
        data=report,
        error=None if status == "SUCCESS" else "RESEARCH_PLAN_INVALID",
    )


def command_project_assess(
    project_root: str,
) -> dict[str, Any]:
    result = assess_project_claims(project_root)

    return _result(
        "project-assess",
        "SUCCESS",
        data=result,
    )


def command_assessment_status(
    project_root: str,
) -> dict[str, Any]:
    result = assessment_status(project_root)

    status = (
        "SUCCESS"
        if result["status"] == "ASSESSED"
        else "BLOCKED"
        if result["status"] == "NOT_RUN"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "assessment-status",
        status,
        data=result,
        error=None if status == "SUCCESS" else result["status"],
    )


def command_contradictions_list(
    project_root: str,
) -> dict[str, Any]:
    return _result(
        "contradictions-list",
        "SUCCESS",
        data=list_contradictions(project_root),
    )


def command_gaps_list(
    project_root: str,
) -> dict[str, Any]:
    return _result(
        "gaps-list",
        "SUCCESS",
        data=list_gaps(project_root),
    )


def command_assessment_verify(
    project_root: str,
) -> dict[str, Any]:
    report = verify_assessment(project_root)

    status = (
        "SUCCESS"
        if report.status == "VALID"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "assessment-verify",
        status,
        data=report,
        error=None if status == "SUCCESS" else "ASSESSMENT_INVALID",
    )


def command_project_extract(
    project_root: str,
) -> dict[str, Any]:
    result = extract_project_knowledge(project_root)

    return _result(
        "project-extract",
        "SUCCESS",
        data=result,
    )


def command_evidence_list(
    project_root: str,
) -> dict[str, Any]:
    return _result(
        "evidence-list",
        "SUCCESS",
        data=list_evidence(project_root),
    )


def command_claims_list(
    project_root: str,
) -> dict[str, Any]:
    return _result(
        "claims-list",
        "SUCCESS",
        data=list_claims(project_root),
    )


def command_knowledge_status(
    project_root: str,
) -> dict[str, Any]:
    result = knowledge_status(project_root)

    status = (
        "SUCCESS"
        if result["status"] == "EXTRACTED"
        else "BLOCKED"
        if result["status"] == "NOT_RUN"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "knowledge-status",
        status,
        data=result,
        error=None if status == "SUCCESS" else result["status"],
    )


def command_knowledge_verify(
    project_root: str,
) -> dict[str, Any]:
    report = verify_knowledge(project_root)

    status = (
        "SUCCESS"
        if report.status == "VALID"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "knowledge-verify",
        status,
        data=report,
        error=None if status == "SUCCESS" else "KNOWLEDGE_INVALID",
    )


def command_source_inspect(
    project_root: str,
    source_id: str,
) -> dict[str, Any]:
    report = inspect_source(project_root, source_id)

    status = (
        "SUCCESS"
        if report["hash_valid"]
        and report["supported_for_ingestion"]
        and not report.get("empty", False)
        else "VALIDATION_FAILURE"
    )

    return _result(
        "source-inspect",
        status,
        data=report,
        error=None if status == "SUCCESS" else "SOURCE_NOT_INGESTIBLE",
    )


def command_project_ingest(project_root: str) -> dict[str, Any]:
    result = ingest_project(project_root)

    status = (
        "SUCCESS"
        if result["status"] == "VALID"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "project-ingest",
        status,
        data=result,
        error=None if status == "SUCCESS" else "INGESTION_INVALID",
    )


def command_ingestion_status(project_root: str) -> dict[str, Any]:
    result = ingestion_status(project_root)

    status = (
        "SUCCESS"
        if result["status"] == "VALID"
        else "BLOCKED"
        if result["status"] == "NOT_RUN"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "ingestion-status",
        status,
        data=result,
        error=None if status == "SUCCESS" else result["status"],
    )


def _shamela_adapter(installation_root: str, discovery_root: str) -> ShamelaLocalSourceAdapter:
    return ShamelaLocalSourceAdapter(installation_root, discovery_root)


def command_shamela_status(installation_root: str, discovery_root: str) -> dict[str, Any]:
    adapter = _shamela_adapter(installation_root, discovery_root)
    return _result(
        "shamela-status",
        "SUCCESS",
        data={
            "adapter_version": "shamela-local-adapter-v1",
            "installation_root": str(adapter.installation_root),
            "master_database": str(adapter.master_path),
            "page_index": str(adapter.page_index),
            "title_index": str(adapter.title_index),
            "installation_fingerprint": adapter.locator_proposal["installation_fingerprint"],
            "access_mode": "READ_ONLY",
        },
    )


def command_shamela_list(
    installation_root: str,
    discovery_root: str,
    category: str | None,
    title: str | None,
    author: str | None,
    book_id: int | None,
    limit: int,
) -> dict[str, Any]:
    adapter = _shamela_adapter(installation_root, discovery_root)
    return _result(
        "shamela-list",
        "SUCCESS",
        data={"books": adapter.list_books(category=category, title=title, author=author, book_id=book_id, limit=limit)},
    )


def command_shamela_inspect(installation_root: str, discovery_root: str, book_id: int) -> dict[str, Any]:
    return _result(
        "shamela-inspect",
        "SUCCESS",
        data=_shamela_adapter(installation_root, discovery_root).inspect_book(book_id),
    )


def command_shamela_import(
    installation_root: str,
    discovery_root: str,
    staging_root: str,
    project_root: str,
    book_id: int,
) -> dict[str, Any]:
    adapter = _shamela_adapter(installation_root, discovery_root)
    staged = adapter.stage_book(book_id, staging_root)
    metadata = adapter.read_metadata(book_id)
    registration = add_source(
        project_root,
        str(Path(staging_root) / staged["body_artifact"]),
        title=metadata["title"],
        language="ar",
        classification="INTERNAL",
        source_type="SHAMELA_LOCAL_BOOK",
        rights_status="RIGHTS_UNVERIFIED",
        source_locator=staged["source_locator"],
        provenance={
            "adapter_version": "shamela-local-adapter-v1",
            "installation_fingerprint": metadata["installation_fingerprint"],
            "database_sha256": metadata["database_sha256"],
            "book_id": book_id,
        },
    )
    ingestion = ingest_project(
        project_root,
        source_ids={registration["source"]["source_id"]},
        working_name="shamela-single-book-ingestion",
    )
    return _result("shamela-import", "SUCCESS" if ingestion["status"] == "VALID" else "VALIDATION_FAILURE", data={"staged": staged, "source": registration["source"], "ingestion": ingestion})


def command_shamela_import_pilot(
    installation_root: str,
    discovery_root: str,
    staging_root: str,
    project_root: str,
) -> dict[str, Any]:
    result = build_pilot_corpus(
        _shamela_adapter(installation_root, discovery_root),
        staging_root,
        project_root=project_root,
    )
    return _result("shamela-import-pilot", "SUCCESS" if result["status"] == "VALID" else "VALIDATION_FAILURE", data=result)


def command_shamela_extract_pilot(
    project_root: str,
    pilot_root: str,
    output_root: str,
    segment_limit_per_book: int | None,
) -> dict[str, Any]:
    result = run_shamela_historical_extraction(
        project_root,
        pilot_root,
        output_root,
        segment_limit_per_book=segment_limit_per_book,
    )
    status = (
        "SUCCESS"
        if result["status"] == "VALID"
        else "VALIDATION_FAILURE"
    )
    return _result(
        "shamela-extract-pilot",
        status,
        data=result,
        error=(
            None
            if status == "SUCCESS"
            else "SHAMELA_EXTRACTION_INVALID"
        ),
    )


def _shamela_audit_root(
    project_root: str,
    audit_root: str | None,
) -> Path:
    working_root = Path(project_paths(project_root).working_root).resolve()
    root = (
        Path(audit_root).resolve()
        if audit_root
        else working_root / "shamela-extraction-quality-audit"
    )
    try:
        root.relative_to(working_root)
    except ValueError as error:
        raise ValueError("AUDIT_ROOT_OUTSIDE_PROJECT_WORKING_ROOT") from error
    return root


def command_shamela_audit_review_status(
    project_root: str,
    audit_root: str | None,
) -> dict[str, Any]:
    root = _shamela_audit_root(project_root, audit_root)
    store = GoldAnnotationStore(root)
    progress = store.progress()
    return _result(
        "shamela-audit-review-status",
        "SUCCESS",
        data={
            "audit_root": str(root),
            "progress": progress,
            "backup_count": len(list(store.backup_root.glob("*.json"))),
            "localhost_only": True,
        },
    )


def command_shamela_audit_review_evaluate(
    project_root: str,
    audit_root: str | None,
) -> dict[str, Any]:
    root = _shamela_audit_root(project_root, audit_root)
    try:
        result = GoldAnnotationStore(root).evaluate()
    except GoldAnnotationValidationError as error:
        status = (
            "BLOCKED"
            if str(error) == "EVALUATION_REQUIRES_ALL_COMPLETED"
            else "VALIDATION_FAILURE"
        )
        return _result(
            "shamela-audit-review-evaluate",
            status,
            error=str(error),
        )
    return _result(
        "shamela-audit-review-evaluate",
        "SUCCESS" if result["status"] == "READY" else "BLOCKED",
        data=result,
        error=None if result["status"] == "READY" else "KNOWLEDGE_GRAPH_GATE_BLOCKED",
    )


def command_shamela_audit_review_serve(
    project_root: str,
    audit_root: str | None,
    host: str,
    port: int,
) -> dict[str, Any]:
    root = _shamela_audit_root(project_root, audit_root)
    server = build_local_workbench_server(root, host=host, port=port)
    print(
        f"Siraj Gold Workbench: http://{host}:{server.server_port}/ "
        "(localhost only; use Ctrl+C to stop)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return _result(
        "shamela-audit-review-serve",
        "SUCCESS",
        data={"audit_root": str(root), "host": host, "port": port},
    )


def command_project_init(
    project_root: str,
    slug: str,
    topic: str,
    language: str,
) -> dict[str, Any]:
    result = initialize_project(
        project_root,
        slug,
        topic,
        language=language,
    )

    return _result(
        "project-init",
        "SUCCESS",
        data=result,
    )


def command_source_add(
    project_root: str,
    source_path: str,
    title: str | None,
    language: str,
    classification: str,
) -> dict[str, Any]:
    result = add_source(
        project_root,
        source_path,
        title=title,
        language=language,
        classification=classification,
    )

    return _result(
        "source-add",
        "SUCCESS",
        data=result,
    )


def command_source_list(project_root: str) -> dict[str, Any]:
    return _result(
        "source-list",
        "SUCCESS",
        data=list_sources(project_root),
    )


def command_project_verify(project_root: str) -> dict[str, Any]:
    report = verify_project(project_root)

    status = (
        "SUCCESS"
        if report.status == "VALID"
        else "VALIDATION_FAILURE"
    )

    return _result(
        "project-verify",
        status,
        data=report,
        error=None if status == "SUCCESS" else "PROJECT_INVALID",
    )


def command_release_verify() -> dict[str, Any]:
    health = command_health()
    config = command_config_validate()

    passed = (
        health["status"] == "SUCCESS"
        and config["status"] == "SUCCESS"
    )

    return _result(
        "release-verify",
        "SUCCESS" if passed else "VALIDATION_FAILURE",
        data={
            "health": health["status"],
            "configuration": config["status"],
            "release": VERSION,
        },
        error=None if passed else "RELEASE_VERIFICATION_FAILED",
    )


def command_production_init(project_root: str, replace: bool) -> dict[str, Any]:
    return _result(
        "production-init",
        "SUCCESS",
        data=initialize_local_production(project_root, replace=replace),
    )


def command_storyboard_build(
    project_root: str,
    ffmpeg: str,
    replace: bool,
) -> dict[str, Any]:
    return _result(
        "storyboard-build",
        "SUCCESS",
        data=build_local_storyboard(
            project_root,
            ffmpeg=ffmpeg,
            replace=replace,
        ),
    )


def command_subtitles_build(
    project_root: str,
    replace: bool,
) -> dict[str, Any]:
    return _result(
        "subtitles-build",
        "SUCCESS",
        data=build_local_subtitles(project_root, replace=replace),
    )


def command_render_build(
    project_root: str,
    ffmpeg: str,
    replace: bool,
) -> dict[str, Any]:
    return _result(
        "render-build",
        "SUCCESS",
        data=build_local_render(
            project_root,
            ffmpeg=ffmpeg,
            replace=replace,
        ),
    )


def command_render_verify(
    project_root: str,
    ffprobe: str,
    replace: bool,
) -> dict[str, Any]:
    result = verify_local_render(
        project_root,
        ffprobe=ffprobe,
        replace=replace,
    )
    return _result(
        "render-verify",
        "SUCCESS" if result["status"] == "VALID" else "VALIDATION_FAILURE",
        data=result,
        error=None if result["status"] == "VALID" else "RENDER_INVALID",
    )


def command_documentary_v2_init(
    project_root: str,
    powershell: str,
    replace: bool,
) -> dict[str, Any]:
    return _result(
        "documentary-v2-init",
        "SUCCESS",
        data=initialize_documentary_v2(
            project_root,
            powershell=powershell,
            replace=replace,
        ),
    )


def command_documentary_v2_storyboard(
    project_root: str,
    ffmpeg: str | None,
    font: str | None,
    replace: bool,
) -> dict[str, Any]:
    return _result(
        "documentary-v2-storyboard",
        "SUCCESS",
        data=build_documentary_v2_storyboard(
            project_root,
            ffmpeg=ffmpeg,
            font_path=font,
            replace=replace,
        ),
    )


def command_documentary_v2_subtitles(
    project_root: str,
    replace: bool,
) -> dict[str, Any]:
    return _result(
        "documentary-v2-subtitles",
        "SUCCESS",
        data=build_documentary_v2_subtitles(project_root, replace=replace),
    )


def command_documentary_v2_render(
    project_root: str,
    ffmpeg: str | None,
    replace: bool,
) -> dict[str, Any]:
    return _result(
        "documentary-v2-render",
        "SUCCESS",
        data=build_documentary_v2_render(
            project_root,
            ffmpeg=ffmpeg,
            replace=replace,
        ),
    )


def command_documentary_v2_verify(
    project_root: str,
    ffmpeg: str | None,
    ffprobe: str | None,
    replace: bool,
) -> dict[str, Any]:
    result = verify_documentary_v2_render(
        project_root,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        replace=replace,
    )
    return _result(
        "documentary-v2-verify",
        "SUCCESS" if result["status"] == "VALID" else "VALIDATION_FAILURE",
        data=result,
        error=None if result["status"] == "VALID" else "DOCUMENTARY_V2_INVALID",
    )


def _documentary_v3_config(
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
) -> DocumentaryV3Config:
    return DocumentaryV3Config(ffmpeg=ffmpeg, ffprobe=ffprobe)


def command_documentary_v3_init(project_root: str, ffmpeg: str | None, replace: bool) -> dict[str, Any]:
    return _result("documentary-v3-init", "SUCCESS", data=initialize_documentary_v3(project_root, config=_documentary_v3_config(ffmpeg=ffmpeg), replace=replace))


def command_documentary_v3_assets(project_root: str, ffmpeg: str | None, replace: bool) -> dict[str, Any]:
    return _result("documentary-v3-assets", "SUCCESS", data=build_documentary_v3_assets(project_root, config=_documentary_v3_config(ffmpeg=ffmpeg), replace=replace))


def command_documentary_v3_subtitles(project_root: str, replace: bool) -> dict[str, Any]:
    return _result("documentary-v3-subtitles", "SUCCESS", data=build_documentary_v3_subtitles(project_root, replace=replace))


def command_documentary_v3_render(project_root: str, ffmpeg: str | None, replace: bool) -> dict[str, Any]:
    return _result("documentary-v3-render", "SUCCESS", data=build_documentary_v3_render(project_root, config=_documentary_v3_config(ffmpeg=ffmpeg), replace=replace))


def command_documentary_v3_verify(project_root: str, ffmpeg: str | None, ffprobe: str | None, replace: bool) -> dict[str, Any]:
    result = verify_documentary_v3_render(project_root, config=_documentary_v3_config(ffmpeg=ffmpeg, ffprobe=ffprobe), replace=replace)
    return _result("documentary-v3-verify", "SUCCESS" if result["status"] == "VALID" else "VALIDATION_FAILURE", data=result, error=None if result["status"] == "VALID" else "DOCUMENTARY_V3_INVALID")


def execute(
    command: str,
    as_json: bool = False,
    **options: Any,
) -> str:
    handlers = {
        "version": lambda: command_version(),
        "health": lambda: command_health(),
        "config-show": lambda: command_config_show(),
        "config-validate": lambda: command_config_validate(),
        "release-verify": lambda: command_release_verify(),
    }

    try:
        if command not in handlers:
            payload = _result(
                command,
                "BLOCKED",
                error="COMMAND_REQUIRES_OPERATIONAL_ARGUMENTS",
            )
        else:
            payload = handlers[command]()
    except Exception as error:
        payload = _result(
            command,
            "INTERNAL_ERROR",
            error=f"{type(error).__name__}:{error}",
        )

    return _format(payload, as_json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="siraj")
    parser.add_argument("--json", action="store_true")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("version")
    subparsers.add_parser("health")
    subparsers.add_parser("config-show")
    subparsers.add_parser("config-validate")
    subparsers.add_parser("release-verify")

    persistence = subparsers.add_parser("persistence")
    persistence_sub = persistence.add_subparsers(
        dest="action",
        required=True,
    )

    persistence_init = persistence_sub.add_parser("init")
    persistence_init.add_argument("--database", required=True)

    persistence_verify = persistence_sub.add_parser("verify")
    persistence_verify.add_argument("--database", required=True)
    persistence_verify.add_argument(
        "--schema-version",
        default="rc-hardening-v1",
    )

    persistence_snapshot = persistence_sub.add_parser("snapshot")
    persistence_snapshot.add_argument("--database", required=True)
    persistence_snapshot.add_argument("--snapshot-id", required=True)
    persistence_snapshot.add_argument("--input", required=True)

    persistence_restore = persistence_sub.add_parser("restore")
    persistence_restore.add_argument("--database", required=True)
    persistence_restore.add_argument("--record-id", required=True)

    migration = subparsers.add_parser("migration")
    migration_sub = migration.add_subparsers(
        dest="action",
        required=True,
    )

    for action in ("plan", "apply"):
        migration_parser = migration_sub.add_parser(action)
        migration_parser.add_argument("--database", required=True)
        migration_parser.add_argument("--target-version", required=True)
        migration_parser.add_argument(
            "--current-version",
            default="rc-hardening-v1",
        )

    export = subparsers.add_parser("export")
    export_sub = export.add_subparsers(dest="action", required=True)
    export_build = export_sub.add_parser("build")
    export_build.add_argument("--input", required=True)
    export_build.add_argument("--output", required=True)
    export_build.add_argument("--replace", action="store_true")

    project = subparsers.add_parser("project")
    project_sub = project.add_subparsers(
        dest="action",
        required=True,
    )

    project_init = project_sub.add_parser("init")
    project_init.add_argument("--root", required=True)
    project_init.add_argument("--slug", required=True)
    project_init.add_argument("--topic", required=True)
    project_init.add_argument("--language", default="ar")

    project_verify = project_sub.add_parser("verify")
    project_verify.add_argument("--root", required=True)

    project_ingest = project_sub.add_parser("ingest")
    project_ingest.add_argument("--root", required=True)

    project_extract = project_sub.add_parser("extract")
    project_extract.add_argument("--root", required=True)

    project_assess = project_sub.add_parser("assess")
    project_assess.add_argument("--root", required=True)

    project_plan_research = project_sub.add_parser("plan-research")
    project_plan_research.add_argument("--root", required=True)

    source = subparsers.add_parser("source")
    source_sub = source.add_subparsers(
        dest="action",
        required=True,
    )

    source_add = source_sub.add_parser("add")
    source_add.add_argument("--project-root", required=True)
    source_add.add_argument("--file", required=True)
    source_add.add_argument("--title")
    source_add.add_argument("--language", default="und")
    source_add.add_argument(
        "--classification",
        default="INTERNAL",
        choices=["PUBLIC", "INTERNAL", "SENSITIVE", "RESTRICTED"],
    )

    source_list = source_sub.add_parser("list")
    source_list.add_argument("--project-root", required=True)

    source_inspect = source_sub.add_parser("inspect")
    source_inspect.add_argument("--project-root", required=True)
    source_inspect.add_argument("--source-id", required=True)

    ingestion = subparsers.add_parser("ingestion")
    ingestion_sub = ingestion.add_subparsers(
        dest="action",
        required=True,
    )

    ingestion_status_parser = ingestion_sub.add_parser("status")
    ingestion_status_parser.add_argument(
        "--project-root",
        required=True,
    )

    shamela = subparsers.add_parser("shamela")
    shamela_sub = shamela.add_subparsers(dest="action", required=True)

    def shamela_paths(item: argparse.ArgumentParser) -> None:
        item.add_argument("--installation-root", required=True)
        item.add_argument("--discovery-root", required=True)

    shamela_status = shamela_sub.add_parser("status")
    shamela_paths(shamela_status)
    shamela_list = shamela_sub.add_parser("list")
    shamela_paths(shamela_list)
    shamela_list.add_argument("--category")
    shamela_list.add_argument("--title")
    shamela_list.add_argument("--author")
    shamela_list.add_argument("--book-id", type=int)
    shamela_list.add_argument("--limit", type=int, default=100)
    shamela_inspect = shamela_sub.add_parser("inspect")
    shamela_paths(shamela_inspect)
    shamela_inspect.add_argument("--book-id", type=int, required=True)
    shamela_import = shamela_sub.add_parser("import")
    shamela_paths(shamela_import)
    shamela_import.add_argument("--staging-root", required=True)
    shamela_import.add_argument("--project-root", required=True)
    shamela_import.add_argument("--book-id", type=int, required=True)
    shamela_import_pilot = shamela_sub.add_parser("import-pilot")
    shamela_paths(shamela_import_pilot)
    shamela_import_pilot.add_argument("--staging-root", required=True)
    shamela_import_pilot.add_argument("--project-root", required=True)
    shamela_extract_pilot = shamela_sub.add_parser("extract-pilot")
    shamela_extract_pilot.add_argument("--project-root", required=True)
    shamela_extract_pilot.add_argument("--pilot-root", required=True)
    shamela_extract_pilot.add_argument("--output-root", required=True)
    shamela_extract_pilot.add_argument(
        "--segment-limit-per-book",
        type=int,
    )
    shamela_audit_review = shamela_sub.add_parser("audit-review")
    shamela_audit_review_sub = shamela_audit_review.add_subparsers(
        dest="audit_review_action",
        required=True,
    )

    def shamela_audit_review_paths(
        item: argparse.ArgumentParser,
    ) -> None:
        item.add_argument("--project-root", required=True)
        item.add_argument("--audit-root")

    shamela_audit_review_serve = shamela_audit_review_sub.add_parser("serve")
    shamela_audit_review_paths(shamela_audit_review_serve)
    shamela_audit_review_serve.add_argument(
        "--host",
        default="127.0.0.1",
    )
    shamela_audit_review_serve.add_argument(
        "--port",
        type=int,
        default=8765,
    )
    shamela_audit_review_status = shamela_audit_review_sub.add_parser("status")
    shamela_audit_review_paths(shamela_audit_review_status)
    shamela_audit_review_evaluate = shamela_audit_review_sub.add_parser("evaluate")
    shamela_audit_review_paths(shamela_audit_review_evaluate)

    evidence = subparsers.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(
        dest="action",
        required=True,
    )
    evidence_list_parser = evidence_sub.add_parser("list")
    evidence_list_parser.add_argument(
        "--project-root",
        required=True,
    )

    claims = subparsers.add_parser("claims")
    claims_sub = claims.add_subparsers(
        dest="action",
        required=True,
    )
    claims_list_parser = claims_sub.add_parser("list")
    claims_list_parser.add_argument(
        "--project-root",
        required=True,
    )

    knowledge = subparsers.add_parser("knowledge")
    knowledge_sub = knowledge.add_subparsers(
        dest="action",
        required=True,
    )

    knowledge_status_parser = knowledge_sub.add_parser("status")
    knowledge_status_parser.add_argument(
        "--project-root",
        required=True,
    )

    knowledge_verify_parser = knowledge_sub.add_parser("verify")
    knowledge_verify_parser.add_argument(
        "--project-root",
        required=True,
    )

    assessment = subparsers.add_parser("assessment")
    assessment_sub = assessment.add_subparsers(
        dest="action",
        required=True,
    )

    assessment_status_parser = assessment_sub.add_parser("status")
    assessment_status_parser.add_argument(
        "--project-root",
        required=True,
    )

    assessment_verify_parser = assessment_sub.add_parser("verify")
    assessment_verify_parser.add_argument(
        "--project-root",
        required=True,
    )

    contradictions = subparsers.add_parser("contradictions")
    contradictions_sub = contradictions.add_subparsers(
        dest="action",
        required=True,
    )
    contradictions_list_parser = contradictions_sub.add_parser("list")
    contradictions_list_parser.add_argument(
        "--project-root",
        required=True,
    )

    gaps = subparsers.add_parser("gaps")
    gaps_sub = gaps.add_subparsers(
        dest="action",
        required=True,
    )
    gaps_list_parser = gaps_sub.add_parser("list")
    gaps_list_parser.add_argument(
        "--project-root",
        required=True,
    )

    research = subparsers.add_parser("research")
    research_sub = research.add_subparsers(
        dest="action",
        required=True,
    )

    research_status_parser = research_sub.add_parser("status")
    research_status_parser.add_argument(
        "--project-root",
        required=True,
    )

    research_tasks_parser = research_sub.add_parser("tasks")
    research_tasks_parser.add_argument(
        "--project-root",
        required=True,
    )

    research_task_show_parser = research_sub.add_parser("task-show")
    research_task_show_parser.add_argument(
        "--project-root",
        required=True,
    )
    research_task_show_parser.add_argument(
        "--task-id",
        required=True,
    )

    research_verify_parser = research_sub.add_parser("verify")
    research_verify_parser.add_argument(
        "--project-root",
        required=True,
    )

    production = subparsers.add_parser("production")
    production_sub = production.add_subparsers(dest="action", required=True)
    production_init = production_sub.add_parser("init")
    production_init.add_argument("--project-root", required=True)
    production_init.add_argument("--replace", action="store_true")
    production_v2 = production_sub.add_parser("documentary-v2-init")
    production_v2.add_argument("--project-root", required=True)
    production_v2.add_argument("--powershell", default="powershell.exe")
    production_v2.add_argument("--replace", action="store_true")
    production_v3 = production_sub.add_parser("documentary-v3-init")
    production_v3.add_argument("--project-root", required=True)
    production_v3.add_argument("--ffmpeg")
    production_v3.add_argument("--replace", action="store_true")

    storyboard = subparsers.add_parser("storyboard")
    storyboard_sub = storyboard.add_subparsers(dest="action", required=True)
    storyboard_build = storyboard_sub.add_parser("build")
    storyboard_build.add_argument("--project-root", required=True)
    storyboard_build.add_argument("--ffmpeg", default="ffmpeg")
    storyboard_build.add_argument("--replace", action="store_true")
    storyboard_v2 = storyboard_sub.add_parser("documentary-v2-build")
    storyboard_v2.add_argument("--project-root", required=True)
    storyboard_v2.add_argument("--ffmpeg")
    storyboard_v2.add_argument("--font")
    storyboard_v2.add_argument("--replace", action="store_true")
    storyboard_v3 = storyboard_sub.add_parser("documentary-v3-assets")
    storyboard_v3.add_argument("--project-root", required=True)
    storyboard_v3.add_argument("--ffmpeg")
    storyboard_v3.add_argument("--replace", action="store_true")

    subtitles = subparsers.add_parser("subtitles")
    subtitles_sub = subtitles.add_subparsers(dest="action", required=True)
    subtitles_build = subtitles_sub.add_parser("build")
    subtitles_build.add_argument("--project-root", required=True)
    subtitles_build.add_argument("--replace", action="store_true")
    subtitles_v2 = subtitles_sub.add_parser("documentary-v2-build")
    subtitles_v2.add_argument("--project-root", required=True)
    subtitles_v2.add_argument("--replace", action="store_true")
    subtitles_v3 = subtitles_sub.add_parser("documentary-v3-build")
    subtitles_v3.add_argument("--project-root", required=True)
    subtitles_v3.add_argument("--replace", action="store_true")

    render = subparsers.add_parser("render")
    render_sub = render.add_subparsers(dest="action", required=True)
    render_dry = render_sub.add_parser("dry-run")
    render_dry.add_argument("--manifest", required=True)
    render_dry.add_argument("--asset-root", required=True)
    render_build = render_sub.add_parser("build")
    render_build.add_argument("--project-root", required=True)
    render_build.add_argument("--ffmpeg", default="ffmpeg")
    render_build.add_argument("--replace", action="store_true")
    render_verify = render_sub.add_parser("verify")
    render_verify.add_argument("--project-root", required=True)
    render_verify.add_argument("--ffprobe", default="ffprobe")
    render_verify.add_argument("--replace", action="store_true")
    render_v2_build = render_sub.add_parser("documentary-v2-build")
    render_v2_build.add_argument("--project-root", required=True)
    render_v2_build.add_argument("--ffmpeg")
    render_v2_build.add_argument("--replace", action="store_true")
    render_v2_verify = render_sub.add_parser("documentary-v2-verify")
    render_v2_verify.add_argument("--project-root", required=True)
    render_v2_verify.add_argument("--ffmpeg")
    render_v2_verify.add_argument("--ffprobe")
    render_v2_verify.add_argument("--replace", action="store_true")
    render_v3_build = render_sub.add_parser("documentary-v3-build")
    render_v3_build.add_argument("--project-root", required=True)
    render_v3_build.add_argument("--ffmpeg")
    render_v3_build.add_argument("--replace", action="store_true")
    render_v3_verify = render_sub.add_parser("documentary-v3-verify")
    render_v3_verify.add_argument("--project-root", required=True)
    render_v3_verify.add_argument("--ffmpeg")
    render_v3_verify.add_argument("--ffprobe")
    render_v3_verify.add_argument("--replace", action="store_true")

    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    command = args.command or "health"

    if command == "version":
        return command_version()
    if command == "health":
        return command_health()
    if command == "config-show":
        return command_config_show()
    if command == "config-validate":
        return command_config_validate()
    if command == "release-verify":
        return command_release_verify()

    if command == "project":
        if args.action == "init":
            return command_project_init(
                args.root,
                args.slug,
                args.topic,
                args.language,
            )
        if args.action == "verify":
            return command_project_verify(args.root)
        if args.action == "ingest":
            return command_project_ingest(args.root)
        if args.action == "extract":
            return command_project_extract(args.root)
        if args.action == "assess":
            return command_project_assess(args.root)
        if args.action == "plan-research":
            return command_project_plan_research(args.root)

    if command == "source":
        if args.action == "add":
            return command_source_add(
                args.project_root,
                args.file,
                args.title,
                args.language,
                args.classification,
            )
        if args.action == "list":
            return command_source_list(args.project_root)
        if args.action == "inspect":
            return command_source_inspect(
                args.project_root,
                args.source_id,
            )

    if command == "ingestion":
        if args.action == "status":
            return command_ingestion_status(args.project_root)

    if command == "shamela":
        if args.action == "status":
            return command_shamela_status(args.installation_root, args.discovery_root)
        if args.action == "list":
            return command_shamela_list(
                args.installation_root,
                args.discovery_root,
                args.category,
                args.title,
                args.author,
                args.book_id,
                args.limit,
            )
        if args.action == "inspect":
            return command_shamela_inspect(args.installation_root, args.discovery_root, args.book_id)
        if args.action == "import":
            return command_shamela_import(
                args.installation_root,
                args.discovery_root,
                args.staging_root,
                args.project_root,
                args.book_id,
            )
        if args.action == "import-pilot":
            return command_shamela_import_pilot(
                args.installation_root,
                args.discovery_root,
                args.staging_root,
                args.project_root,
            )
        if args.action == "extract-pilot":
            return command_shamela_extract_pilot(
                args.project_root,
                args.pilot_root,
                args.output_root,
                args.segment_limit_per_book,
            )
        if args.action == "audit-review":
            if args.audit_review_action == "serve":
                return command_shamela_audit_review_serve(
                    args.project_root,
                    args.audit_root,
                    args.host,
                    args.port,
                )
            if args.audit_review_action == "status":
                return command_shamela_audit_review_status(
                    args.project_root,
                    args.audit_root,
                )
            if args.audit_review_action == "evaluate":
                return command_shamela_audit_review_evaluate(
                    args.project_root,
                    args.audit_root,
                )

    if command == "evidence":
        if args.action == "list":
            return command_evidence_list(args.project_root)

    if command == "claims":
        if args.action == "list":
            return command_claims_list(args.project_root)

    if command == "knowledge":
        if args.action == "status":
            return command_knowledge_status(args.project_root)
        if args.action == "verify":
            return command_knowledge_verify(args.project_root)

    if command == "assessment":
        if args.action == "status":
            return command_assessment_status(args.project_root)
        if args.action == "verify":
            return command_assessment_verify(args.project_root)

    if command == "contradictions":
        if args.action == "list":
            return command_contradictions_list(args.project_root)

    if command == "gaps":
        if args.action == "list":
            return command_gaps_list(args.project_root)

    if command == "research":
        if args.action == "status":
            return command_research_status(args.project_root)
        if args.action == "tasks":
            return command_research_tasks(args.project_root)
        if args.action == "task-show":
            return command_research_task_show(
                args.project_root,
                args.task_id,
            )
        if args.action == "verify":
            return command_research_verify(args.project_root)

    if command == "production":
        if args.action == "init":
            return command_production_init(args.project_root, args.replace)
        if args.action == "documentary-v2-init":
            return command_documentary_v2_init(
                args.project_root,
                args.powershell,
                args.replace,
            )
        if args.action == "documentary-v3-init":
            return command_documentary_v3_init(
                args.project_root,
                args.ffmpeg,
                args.replace,
            )

    if command == "storyboard":
        if args.action == "build":
            return command_storyboard_build(
                args.project_root,
                args.ffmpeg,
                args.replace,
            )
        if args.action == "documentary-v2-build":
            return command_documentary_v2_storyboard(
                args.project_root,
                args.ffmpeg,
                args.font,
                args.replace,
            )
        if args.action == "documentary-v3-assets":
            return command_documentary_v3_assets(
                args.project_root,
                args.ffmpeg,
                args.replace,
            )

    if command == "subtitles":
        if args.action == "build":
            return command_subtitles_build(args.project_root, args.replace)
        if args.action == "documentary-v2-build":
            return command_documentary_v2_subtitles(args.project_root, args.replace)
        if args.action == "documentary-v3-build":
            return command_documentary_v3_subtitles(args.project_root, args.replace)

    if command == "persistence":
        if args.action == "init":
            return command_persistence_init(args.database)
        if args.action == "verify":
            return command_persistence_verify(
                args.database,
                args.schema_version,
            )
        if args.action == "snapshot":
            return command_persistence_snapshot(
                args.database,
                args.snapshot_id,
                args.input,
            )
        if args.action == "restore":
            return command_persistence_restore(
                args.database,
                args.record_id,
            )

    if command == "migration":
        return command_migration(
            args.database,
            args.target_version,
            apply=args.action == "apply",
            current_version=args.current_version,
        )

    if command == "export" and args.action == "build":
        return command_export_build(
            args.input,
            args.output,
            args.replace,
        )

    if command == "render":
        if args.action == "dry-run":
            return command_render_dry_run(
                args.manifest,
                args.asset_root,
            )
        if args.action == "build":
            return command_render_build(
                args.project_root,
                args.ffmpeg,
                args.replace,
            )
        if args.action == "verify":
            return command_render_verify(
                args.project_root,
                args.ffprobe,
                args.replace,
            )
        if args.action == "documentary-v2-build":
            return command_documentary_v2_render(
                args.project_root,
                args.ffmpeg,
                args.replace,
            )
        if args.action == "documentary-v2-verify":
            return command_documentary_v2_verify(
                args.project_root,
                args.ffmpeg,
                args.ffprobe,
                args.replace,
            )
        if args.action == "documentary-v3-build":
            return command_documentary_v3_render(
                args.project_root,
                args.ffmpeg,
                args.replace,
            )
        if args.action == "documentary-v3-verify":
            return command_documentary_v3_verify(
                args.project_root,
                args.ffmpeg,
                args.ffprobe,
                args.replace,
            )

    return _result(
        command,
        "INVALID_INPUT",
        error="UNKNOWN_COMMAND",
    )



def _configure_console_encoding() -> None:
    """Configure CLI streams for deterministic UTF-8 output."""

    import sys

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)

        if stream is None:
            continue

        reconfigure = getattr(stream, "reconfigure", None)

        if not callable(reconfigure):
            continue

        try:
            reconfigure(
                encoding="utf-8",
                errors=(
                    "strict"
                    if stream_name == "stdout"
                    else "replace"
                ),
            )
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    parser = build_parser()

    # Preserve compatibility with both:
    #   siraj --json health
    #   siraj health --json
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    if "--json" in effective_argv:
        effective_argv = [
            "--json",
            *[item for item in effective_argv if item != "--json"],
        ]

    try:
        args = parser.parse_args(effective_argv)
        payload = dispatch(args)
    except FileNotFoundError as error:
        payload = _result(
            "cli",
            "DEPENDENCY_FAILURE",
            error=str(error),
        )
        args = argparse.Namespace(json="--json" in effective_argv)
    except PermissionError as error:
        payload = _result(
            "cli",
            "POLICY_DENIAL",
            error=str(error),
        )
        args = argparse.Namespace(json="--json" in effective_argv)
    except ValueError as error:
        payload = _result(
            "cli",
            "INVALID_INPUT",
            error=str(error),
        )
        args = argparse.Namespace(json="--json" in effective_argv)
    except Exception as error:
        payload = _result(
            "cli",
            "INTERNAL_ERROR",
            error=f"{type(error).__name__}:{error}",
        )
        args = argparse.Namespace(json="--json" in effective_argv)

    print(_format(payload, bool(getattr(args, "json", False))))
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
