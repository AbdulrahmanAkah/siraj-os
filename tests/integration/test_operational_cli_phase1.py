import json
from pathlib import Path
import sqlite3

from src.application.cli_v2 import EXIT_CODES, execute, main


def test_compatibility_execute_still_returns_stable_json():
    payload = json.loads(execute("health", True))

    assert payload["status"] == "SUCCESS"
    assert payload["version"] == "0.1.0-rc.2"
    assert payload["exit_code"] == EXIT_CODES["SUCCESS"]


def test_persistence_init_creates_real_sqlite_database(tmp_path, capsys):
    database = tmp_path / "project.sqlite"

    result = main([
        "--json",
        "persistence",
        "init",
        "--database",
        str(database),
    ])

    payload = json.loads(capsys.readouterr().out)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["status"] == "SUCCESS"
    assert database.is_file()

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert "schema_metadata" in tables
    assert "persisted_records" in tables


def test_persistence_verify_fails_for_missing_database(tmp_path, capsys):
    database = tmp_path / "missing.sqlite"

    result = main([
        "--json",
        "persistence",
        "verify",
        "--database",
        str(database),
    ])

    payload = json.loads(capsys.readouterr().out)

    assert result == EXIT_CODES["DEPENDENCY_FAILURE"]
    assert payload["status"] == "DEPENDENCY_FAILURE"
    assert payload["error"] == "DATABASE_NOT_FOUND"


def test_snapshot_and_restore_execute_real_storage(tmp_path, capsys):
    database = tmp_path / "project.sqlite"
    source = tmp_path / "snapshot.json"
    source.write_text(
        json.dumps(
            {"title": "الحلقة الأولى", "api_key": "do-not-store"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert main([
        "--json",
        "persistence",
        "init",
        "--database",
        str(database),
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "persistence",
        "snapshot",
        "--database",
        str(database),
        "--snapshot-id",
        "pilot-episode",
        "--input",
        str(source),
    ]) == 0

    snapshot_payload = json.loads(capsys.readouterr().out)
    record_id = snapshot_payload["data"]["record_ids"][0]

    assert main([
        "--json",
        "persistence",
        "restore",
        "--database",
        str(database),
        "--record-id",
        record_id,
    ]) == 0

    restored_payload = json.loads(capsys.readouterr().out)
    restored = restored_payload["data"]["restored"][record_id]

    assert restored["title"] == "الحلقة الأولى"
    assert restored["api_key"] == "REDACTED"


def test_export_build_creates_real_artifacts_and_manifest(
    tmp_path,
    capsys,
):
    output = tmp_path / "episode-export"
    package = tmp_path / "package.json"

    package.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "type": "json",
                        "path": "project.json",
                        "content": {
                            "project_id": "pilot",
                            "topic": "Pilot episode",
                        },
                    },
                    {
                        "type": "markdown",
                        "path": "script.md",
                        "content": "# Script\n\nPilot narration.\n",
                    },
                ],
                "subtitles": [
                    {
                        "cue_id": "cue-1",
                        "start_ms": 0,
                        "end_ms": 1500,
                        "text": "Pilot narration.",
                    }
                ],
                "credits": [
                    {
                        "role": "Research",
                        "name": "SIRAJ",
                    }
                ],
                "sources": [
                    {
                        "source_id": "source-1",
                        "title": "Pilot Source",
                    }
                ],
                "limitations": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = main([
        "--json",
        "export",
        "build",
        "--input",
        str(package),
        "--output",
        str(output),
    ])

    payload = json.loads(capsys.readouterr().out)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["status"] == "SUCCESS"
    assert (output / "project.json").is_file()
    assert (output / "script.md").is_file()
    assert (output / "subtitles.srt").is_file()
    assert (output / "subtitles.vtt").is_file()
    assert (output / "credits.md").is_file()
    assert (output / "source-appendix.md").is_file()
    assert (output / "export-manifest.json").is_file()


def test_export_rejects_relative_output_root(tmp_path, capsys):
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps({
            "artifacts": [
                {
                    "type": "json",
                    "path": "project.json",
                    "content": {},
                }
            ]
        }),
        encoding="utf-8",
    )

    result = main([
        "--json",
        "export",
        "build",
        "--input",
        str(package),
        "--output",
        "relative-output",
    ])

    payload = json.loads(capsys.readouterr().out)

    assert result == EXIT_CODES["INVALID_INPUT"]
    assert payload["status"] == "INVALID_INPUT"
    assert "OUTPUT_ROOT_MUST_BE_ABSOLUTE" in payload["error"]


def test_render_dry_run_returns_blocked_for_missing_asset(
    tmp_path,
    capsys,
):
    manifest = tmp_path / "render-manifest.json"
    manifest.write_text(
        json.dumps({
            "assets": [
                {
                    "asset_id": "missing-asset",
                    "path": str(tmp_path / "missing.jpg"),
                    "rights_status": "RIGHTS_UNVERIFIED",
                }
            ],
            "tracks": {},
            "dependencies": [],
        }),
        encoding="utf-8",
    )

    result = main([
        "--json",
        "render",
        "dry-run",
        "--manifest",
        str(manifest),
        "--asset-root",
        str(tmp_path),
    ])

    payload = json.loads(capsys.readouterr().out)

    assert result == EXIT_CODES["BLOCKED"]
    assert payload["status"] == "BLOCKED"
    assert payload["data"]["status"] == "BLOCKED"
