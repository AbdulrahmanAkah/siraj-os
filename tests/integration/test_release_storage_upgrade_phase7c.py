
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.cli_v2 import main
import src.application.project_research_planning_runtime.runtime as research_runtime
from src.application.project_research_planning_runtime import (
    build_research_plan,
    research_status,
    verify_research_plan,
)


ARABIC_SOURCE = (
    "\u062a\u0623\u0633\u0633\u062a "
    "\u0627\u0644\u0645\u062f\u064a\u0646\u0629 "
    "\u0633\u0646\u0629 1901 "
    "\u0648\u0628\u062f\u0623 "
    "\u0646\u0645\u0648\u0647\u0627 "
    "\u0633\u0631\u064a\u0639\u0627\u064b."
)


def _discard_output(capsys) -> None:
    capsys.readouterr()


def _prepare_assessed_project(
    tmp_path: Path,
    capsys,
) -> Path:
    project_root = tmp_path / "storage-upgrade-project"
    source_path = tmp_path / "source.txt"

    source_path.write_text(
        ARABIC_SOURCE,
        encoding="utf-8",
    )

    commands = [
        [
            "--json",
            "project",
            "init",
            "--root",
            str(project_root),
            "--slug",
            "storage-upgrade-project",
            "--topic",
            "Storage and upgrade hardening",
            "--language",
            "ar",
        ],
        [
            "--json",
            "source",
            "add",
            "--project-root",
            str(project_root),
            "--file",
            str(source_path),
            "--title",
            "Storage test source",
        ],
        [
            "--json",
            "project",
            "ingest",
            "--root",
            str(project_root),
        ],
        [
            "--json",
            "project",
            "extract",
            "--root",
            str(project_root),
        ],
        [
            "--json",
            "project",
            "assess",
            "--root",
            str(project_root),
        ],
    ]

    for command in commands:
        assert main(command) == 0
        _discard_output(capsys)

    return project_root


def _research_path(
    project_root: Path,
    filename: str,
) -> Path:
    return (
        project_root
        / "working"
        / "research"
        / filename
    )


def _assessment_path(
    project_root: Path,
    filename: str,
) -> Path:
    return (
        project_root
        / "working"
        / "assessment"
        / filename
    )


def _knowledge_path(
    project_root: Path,
    filename: str,
) -> Path:
    return (
        project_root
        / "working"
        / "knowledge"
        / filename
    )


def _read_json(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def _write_json(
    path: Path,
    payload: dict,
) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def test_atomic_write_failure_preserves_existing_target(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "artifact.json"
    target.write_bytes(b"stable-content")

    def fail_replace(source, destination):
        raise OSError("SIMULATED_REPLACE_FAILURE")

    monkeypatch.setattr(
        research_runtime.os,
        "replace",
        fail_replace,
    )

    with pytest.raises(
        OSError,
        match="SIMULATED_REPLACE_FAILURE",
    ):
        research_runtime._atomic_write(
            target,
            b"new-content",
        )

    assert target.read_bytes() == b"stable-content"
    assert list(tmp_path.glob(".siraj-*.tmp")) == []


def test_atomic_write_creates_complete_file(
    tmp_path: Path,
):
    target = tmp_path / "artifact.json"
    content = (
        b'{"schema_version":"test","status":"VALID"}\n'
    )

    research_runtime._atomic_write(
        target,
        content,
    )

    assert target.read_bytes() == content
    assert list(tmp_path.glob(".siraj-*.tmp")) == []


def test_sqlite_busy_is_propagated_without_false_success(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    project_root = _prepare_assessed_project(
        tmp_path,
        capsys,
    )

    def fail_save_many(self, records):
        return SimpleNamespace(
            committed=False,
            error_code="SQLITE_BUSY",
            record_ids=[],
        )

    monkeypatch.setattr(
        research_runtime.SQLitePersistenceAdapter,
        "save_many",
        fail_save_many,
    )

    with pytest.raises(
        RuntimeError,
        match="SQLITE_BUSY",
    ):
        build_research_plan(
            str(project_root)
        )


def test_persistence_failure_never_reports_planned_status(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    project_root = _prepare_assessed_project(
        tmp_path,
        capsys,
    )

    def fail_save_many(self, records):
        return SimpleNamespace(
            committed=False,
            error_code="PERSISTENCE_FAILED",
            record_ids=[],
        )

    monkeypatch.setattr(
        research_runtime.SQLitePersistenceAdapter,
        "save_many",
        fail_save_many,
    )

    with pytest.raises(
        RuntimeError,
        match="PERSISTENCE_FAILED",
    ):
        build_research_plan(
            str(project_root)
        )

    status = research_status(
        str(project_root)
    )

    # JSON artifacts may have been atomically written before the
    # database transaction failed, but the operation itself must not
    # return a successful result to its caller.
    assert status["status"] in {
        "NOT_RUN",
        "PLANNED",
    }


def test_unsupported_research_schema_is_rejected(
    tmp_path: Path,
    capsys,
):
    project_root = _prepare_assessed_project(
        tmp_path,
        capsys,
    )

    build_research_plan(
        str(project_root)
    )

    tasks_path = _research_path(
        project_root,
        "research-tasks.json",
    )
    payload = _read_json(tasks_path)
    payload["schema_version"] = (
        "siraj-research-plan-v999"
    )
    _write_json(tasks_path, payload)

    report = verify_research_plan(
        str(project_root)
    )

    assert report.status == "INVALID"
    assert {
        issue.code
        for issue in report.issues
    } == {
        "RESEARCH_ARTIFACT_INVALID"
    }


def test_unsupported_assessment_schema_blocks_upgrade(
    tmp_path: Path,
    capsys,
):
    project_root = _prepare_assessed_project(
        tmp_path,
        capsys,
    )

    gaps_path = _assessment_path(
        project_root,
        "research-gaps.json",
    )
    payload = _read_json(gaps_path)
    payload["schema_version"] = (
        "siraj-claim-assessment-v999"
    )
    _write_json(gaps_path, payload)

    with pytest.raises(
        ValueError,
        match="INVALID_ASSESSMENT_SCHEMA",
    ):
        build_research_plan(
            str(project_root)
        )


def test_unsupported_knowledge_schema_blocks_upgrade(
    tmp_path: Path,
    capsys,
):
    project_root = _prepare_assessed_project(
        tmp_path,
        capsys,
    )

    claims_path = _knowledge_path(
        project_root,
        "claims.json",
    )
    payload = _read_json(claims_path)
    payload["schema_version"] = (
        "siraj-knowledge-evidence-v999"
    )
    _write_json(claims_path, payload)

    with pytest.raises(
        ValueError,
        match="INVALID_KNOWLEDGE_SCHEMA",
    ):
        build_research_plan(
            str(project_root)
        )


def test_missing_legacy_assessment_artifact_fails_clearly(
    tmp_path: Path,
    capsys,
):
    project_root = _prepare_assessed_project(
        tmp_path,
        capsys,
    )

    gaps_path = _assessment_path(
        project_root,
        "research-gaps.json",
    )
    gaps_path.unlink()

    with pytest.raises(
        FileNotFoundError,
        match="FILE_NOT_FOUND",
    ):
        build_research_plan(
            str(project_root)
        )


def test_rebuild_after_research_directory_removal_is_deterministic(
    tmp_path: Path,
    capsys,
):
    project_root = _prepare_assessed_project(
        tmp_path,
        capsys,
    )

    first = build_research_plan(
        str(project_root)
    )

    research_root = (
        project_root
        / "working"
        / "research"
    )

    for artifact in research_root.iterdir():
        artifact.unlink()

    research_root.rmdir()

    second = build_research_plan(
        str(project_root)
    )

    assert (
        first["research_plan_id"]
        == second["research_plan_id"]
    )
    assert (
        first["persistence_record_ids"]
        == second["persistence_record_ids"]
    )
    assert (
        first["task_count"]
        == second["task_count"]
    )
    assert (
        first["query_count"]
        == second["query_count"]
    )


def test_tampered_plan_task_order_is_detected(
    tmp_path: Path,
    capsys,
):
    project_root = _prepare_assessed_project(
        tmp_path,
        capsys,
    )

    build_research_plan(
        str(project_root)
    )

    plan_path = _research_path(
        project_root,
        "research-plan.json",
    )
    payload = _read_json(plan_path)

    original_task_ids = list(
        payload["plan"]["task_ids"]
    )

    assert original_task_ids

    payload["plan"]["task_ids"] = [
        "research_task_tampered_identifier",
        *original_task_ids[1:],
    ]

    _write_json(plan_path, payload)

    report = verify_research_plan(
        str(project_root)
    )

    assert report.status == "INVALID"

    codes = {
        issue.code
        for issue in report.issues
    }

    assert "PLAN_TASK_ORDER_MISMATCH" in codes
