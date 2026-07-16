import json
from pathlib import Path

from src.application.cli_v2 import EXIT_CODES, main


def _read_output(capsys):
    return json.loads(capsys.readouterr().out)


def test_project_init_creates_operational_project(tmp_path, capsys):
    project_root = tmp_path / "pilot"

    result = main([
        "--json",
        "project",
        "init",
        "--root",
        str(project_root),
        "--slug",
        "youtube-pilot",
        "--topic",
        "Pilot historical documentary",
        "--language",
        "ar",
    ])

    payload = _read_output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["status"] == "SUCCESS"
    assert (project_root / "project.json").is_file()
    assert (project_root / "sources.json").is_file()
    assert (project_root / "siraj.sqlite").is_file()
    assert (project_root / "sources" / "raw").is_dir()
    assert (project_root / "exports").is_dir()
    assert (project_root / "working").is_dir()
    assert (project_root / "manifests").is_dir()


def test_project_init_rejects_existing_project(tmp_path, capsys):
    project_root = tmp_path / "pilot"

    first = [
        "--json",
        "project",
        "init",
        "--root",
        str(project_root),
        "--slug",
        "youtube-pilot",
        "--topic",
        "Pilot",
    ]

    assert main(first) == EXIT_CODES["SUCCESS"]
    capsys.readouterr()

    result = main(first)
    payload = _read_output(capsys)

    assert result == EXIT_CODES["INVALID_INPUT"]
    assert payload["status"] == "INVALID_INPUT"
    assert payload["error"] == "PROJECT_ALREADY_INITIALIZED"


def test_source_add_copies_persists_and_deduplicates(tmp_path, capsys):
    project_root = tmp_path / "pilot"
    source_file = tmp_path / "source-ar.txt"
    source_file.write_text(
        "هذا مصدر تاريخي تجريبي.",
        encoding="utf-8",
    )

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(project_root),
        "--slug",
        "youtube-pilot",
        "--topic",
        "Pilot",
    ]) == 0
    capsys.readouterr()

    result = main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(project_root),
        "--file",
        str(source_file),
        "--title",
        "مصدر تجريبي",
        "--language",
        "ar",
        "--classification",
        "PUBLIC",
    ])

    payload = _read_output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["data"]["added"] is True
    assert payload["data"]["duplicate"] is False

    source = payload["data"]["source"]
    stored = project_root / source["stored_path"]

    assert stored.is_file()
    assert stored.read_text(encoding="utf-8") == source_file.read_text(
        encoding="utf-8"
    )
    assert source["persistence_record_id"].startswith("sqlite_record_")

    duplicate_result = main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(project_root),
        "--file",
        str(source_file),
    ])

    duplicate_payload = _read_output(capsys)

    assert duplicate_result == EXIT_CODES["SUCCESS"]
    assert duplicate_payload["data"]["duplicate"] is True
    assert duplicate_payload["data"]["added"] is False


def test_source_list_returns_stable_registry(tmp_path, capsys):
    project_root = tmp_path / "pilot"
    source_file = tmp_path / "source.txt"
    source_file.write_text("source", encoding="utf-8")

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(project_root),
        "--slug",
        "youtube-pilot",
        "--topic",
        "Pilot",
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(project_root),
        "--file",
        str(source_file),
    ]) == 0
    capsys.readouterr()

    result = main([
        "--json",
        "source",
        "list",
        "--project-root",
        str(project_root),
    ])

    payload = _read_output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["data"]["source_count"] == 1
    assert len(payload["data"]["sources"]) == 1


def test_project_verify_passes_for_intact_project(tmp_path, capsys):
    project_root = tmp_path / "pilot"
    source_file = tmp_path / "source.txt"
    source_file.write_text("source", encoding="utf-8")

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(project_root),
        "--slug",
        "youtube-pilot",
        "--topic",
        "Pilot",
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(project_root),
        "--file",
        str(source_file),
    ]) == 0
    capsys.readouterr()

    result = main([
        "--json",
        "project",
        "verify",
        "--root",
        str(project_root),
    ])

    payload = _read_output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["status"] == "SUCCESS"
    assert payload["data"]["status"] == "VALID"
    assert payload["data"]["source_count"] == 1
    assert payload["data"]["verified_source_count"] == 1


def test_project_verify_detects_source_tampering(tmp_path, capsys):
    project_root = tmp_path / "pilot"
    source_file = tmp_path / "source.txt"
    source_file.write_text("original", encoding="utf-8")

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(project_root),
        "--slug",
        "youtube-pilot",
        "--topic",
        "Pilot",
    ]) == 0
    capsys.readouterr()

    assert main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(project_root),
        "--file",
        str(source_file),
    ]) == 0

    added = _read_output(capsys)
    stored_path = project_root / added["data"]["source"]["stored_path"]
    stored_path.write_text("tampered", encoding="utf-8")

    result = main([
        "--json",
        "project",
        "verify",
        "--root",
        str(project_root),
    ])

    payload = _read_output(capsys)

    assert result == EXIT_CODES["VALIDATION_FAILURE"]
    assert payload["status"] == "VALIDATION_FAILURE"
    assert payload["data"]["status"] == "INVALID"

    codes = {
        issue["code"]
        for issue in payload["data"]["issues"]
    }

    assert "SOURCE_HASH_MISMATCH" in codes


def test_source_add_rejects_missing_file(tmp_path, capsys):
    project_root = tmp_path / "pilot"

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(project_root),
        "--slug",
        "youtube-pilot",
        "--topic",
        "Pilot",
    ]) == 0
    capsys.readouterr()

    result = main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(project_root),
        "--file",
        str(tmp_path / "missing.txt"),
    ])

    payload = _read_output(capsys)

    assert result == EXIT_CODES["DEPENDENCY_FAILURE"]
    assert payload["status"] == "DEPENDENCY_FAILURE"
    assert "SOURCE_NOT_FOUND" in payload["error"]
