from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import platform
import sys
from typing import Any

from src.application.project_ingestion_runtime import (
    ingest_project,
    ingestion_status,
    inspect_source,
)

from src.application.project_runtime import (
    add_source,
    initialize_project,
    list_sources,
    verify_project,
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

VERSION = "0.1.0-rc.1"

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

    render = subparsers.add_parser("render")
    render_sub = render.add_subparsers(dest="action", required=True)
    render_dry = render_sub.add_parser("dry-run")
    render_dry.add_argument("--manifest", required=True)
    render_dry.add_argument("--asset-root", required=True)

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

    if command == "render" and args.action == "dry-run":
        return command_render_dry_run(
            args.manifest,
            args.asset_root,
        )

    return _result(
        command,
        "INVALID_INPUT",
        error="UNKNOWN_COMMAND",
    )


def main(argv: list[str] | None = None) -> int:
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
