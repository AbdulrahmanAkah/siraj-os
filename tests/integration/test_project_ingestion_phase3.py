import json
from pathlib import Path

from src.application.cli_v2 import EXIT_CODES, main


def _output(capsys):
    return json.loads(capsys.readouterr().out)


def _initialize_project(tmp_path, capsys):
    root = tmp_path / "pilot"

    assert main([
        "--json",
        "project",
        "init",
        "--root",
        str(root),
        "--slug",
        "youtube-pilot",
        "--topic",
        "Pilot documentary",
        "--language",
        "ar",
    ]) == 0

    capsys.readouterr()
    return root


def _add_source(root, source_file, capsys):
    assert main([
        "--json",
        "source",
        "add",
        "--project-root",
        str(root),
        "--file",
        str(source_file),
        "--language",
        "ar",
        "--classification",
        "PUBLIC",
    ]) == 0

    return _output(capsys)


def test_source_inspect_reports_real_text_properties(tmp_path, capsys):
    root = _initialize_project(tmp_path, capsys)
    source = tmp_path / "source.txt"
    source.write_text(
        "سطر أول\nسطر ثان",
        encoding="utf-8",
    )

    added = _add_source(root, source, capsys)
    source_id = added["data"]["source"]["source_id"]

    result = main([
        "--json",
        "source",
        "inspect",
        "--project-root",
        str(root),
        "--source-id",
        source_id,
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["data"]["hash_valid"] is True
    assert payload["data"]["supported_for_ingestion"] is True
    assert payload["data"]["line_count"] == 2
    assert payload["data"]["empty"] is False


def test_ingestion_status_is_blocked_before_run(tmp_path, capsys):
    root = _initialize_project(tmp_path, capsys)

    result = main([
        "--json",
        "ingestion",
        "status",
        "--project-root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["BLOCKED"]
    assert payload["status"] == "BLOCKED"
    assert payload["data"]["status"] == "NOT_RUN"


def test_project_ingest_creates_real_normalized_artifacts(
    tmp_path,
    capsys,
):
    root = _initialize_project(tmp_path, capsys)

    first = tmp_path / "first.txt"
    second = tmp_path / "second.md"

    first.write_text(
        "المصدر التاريخي الأول.\r\nالسطر الثاني.",
        encoding="utf-8",
    )
    second.write_text(
        "# Source\n\nSecond historical source.",
        encoding="utf-8",
    )

    _add_source(root, first, capsys)
    _add_source(root, second, capsys)

    result = main([
        "--json",
        "project",
        "ingest",
        "--root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["status"] == "SUCCESS"
    assert payload["data"]["processed_count"] == 2
    assert payload["data"]["accepted_count"] == 2
    assert payload["data"]["rejected_count"] == 0

    ingestion = root / "working" / "ingestion"

    assert (ingestion / "ingestion-plan.json").is_file()
    assert (ingestion / "ingestion-result.json").is_file()
    assert (ingestion / "normalized-sources.json").is_file()
    assert (ingestion / "fingerprints.json").is_file()

    registry = json.loads(
        (ingestion / "normalized-sources.json").read_text(
            encoding="utf-8"
        )
    )

    assert len(registry["sources"]) == 2

    for item in registry["sources"]:
        normalized = ingestion / item["path"]
        assert normalized.is_file()
        assert normalized.read_bytes()
        assert "\r" not in normalized.read_text(encoding="utf-8")


def test_ingestion_is_deterministic_across_replay(tmp_path, capsys):
    root = _initialize_project(tmp_path, capsys)
    source = tmp_path / "source.txt"
    source.write_text("stable source", encoding="utf-8")

    _add_source(root, source, capsys)

    assert main([
        "--json",
        "project",
        "ingest",
        "--root",
        str(root),
    ]) == 0

    first = _output(capsys)

    assert main([
        "--json",
        "project",
        "ingest",
        "--root",
        str(root),
    ]) == 0

    second = _output(capsys)

    assert (
        first["data"]["execution_id"]
        == second["data"]["execution_id"]
    )
    assert first["data"]["plan_id"] == second["data"]["plan_id"]


def test_ingestion_status_reports_valid_execution(tmp_path, capsys):
    root = _initialize_project(tmp_path, capsys)
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")

    _add_source(root, source, capsys)

    assert main([
        "--json",
        "project",
        "ingest",
        "--root",
        str(root),
    ]) == 0
    capsys.readouterr()

    result = main([
        "--json",
        "ingestion",
        "status",
        "--project-root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["SUCCESS"]
    assert payload["data"]["status"] == "VALID"
    assert payload["data"]["processed_count"] == 1
    assert payload["data"]["accepted_count"] == 1


def test_project_ingest_rejects_unsupported_binary_source(
    tmp_path,
    capsys,
):
    root = _initialize_project(tmp_path, capsys)
    source = tmp_path / "image.bin"
    source.write_bytes(b"\x00\x01\x02")

    _add_source(root, source, capsys)

    result = main([
        "--json",
        "project",
        "ingest",
        "--root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["INVALID_INPUT"]
    assert payload["status"] == "INVALID_INPUT"
    assert "UNSUPPORTED_SOURCE_TYPE" in payload["error"]


def test_project_ingest_requires_registered_sources(tmp_path, capsys):
    root = _initialize_project(tmp_path, capsys)

    result = main([
        "--json",
        "project",
        "ingest",
        "--root",
        str(root),
    ])

    payload = _output(capsys)

    assert result == EXIT_CODES["INVALID_INPUT"]
    assert payload["error"] == "NO_SOURCES_REGISTERED"
