from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def _run_cli(
    arguments: list[str],
    *,
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )

    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        [sys.executable, "-m", "src.application.cli_v2", *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def _prepare_project(
    repository_root: Path,
    project_root: Path,
    source_path: Path,
) -> None:
    commands = [
        [
            "--json",
            "project",
            "init",
            "--root",
            str(project_root),
            "--slug",
            "unicode-release-test",
            "--topic",
            "اختبار إطلاق عربي",
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
            "مصدر عربي",
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
        [
            "--json",
            "project",
            "plan-research",
            "--root",
            str(project_root),
        ],
    ]

    for command in commands:
        result = _run_cli(
            command,
            cwd=repository_root,
        )

        assert result.returncode == 0, (
            f"Command failed: {command}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )


def test_cli_json_unicode_output_through_subprocess(
    tmp_path,
):
    repository_root = Path(__file__).resolve().parents[2]
    project_root = tmp_path / "مشروع تجريبي"
    source_path = tmp_path / "مصدر عربي.txt"

    source_path.write_text(
        "تأسست المدينة سنة 1901 وبدأ نموها سريعاً.",
        encoding="utf-8",
    )

    _prepare_project(
        repository_root,
        project_root,
        source_path,
    )

    result = _run_cli(
        [
            "--json",
            "research",
            "tasks",
            "--project-root",
            str(project_root),
        ],
        cwd=repository_root,
    )

    assert result.returncode == 0
    assert result.stderr == ""

    payload = json.loads(result.stdout)

    assert payload["status"] == "SUCCESS"
    assert payload["data"]["task_count"] == 1
    assert "تأسست المدينة" in payload["data"]["tasks"][0]["objective"]


def test_cli_json_output_remains_valid_when_piped(
    tmp_path,
):
    repository_root = Path(__file__).resolve().parents[2]
    project_root = tmp_path / "pipeline-project"
    source_path = tmp_path / "source.txt"

    source_path.write_text(
        "أعلن الملك فيصل القرار سنة 1921.",
        encoding="utf-8",
    )

    _prepare_project(
        repository_root,
        project_root,
        source_path,
    )

    command = [
        sys.executable,
        "-m",
        "src.application.cli_v2",
        "--json",
        "research",
        "tasks",
        "--project-root",
        str(project_root),
    ]

    producer = subprocess.Popen(
        command,
        cwd=repository_root,
        env={
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = producer.communicate()

    assert producer.returncode == 0
    assert stderr.decode("utf-8") == ""

    payload = json.loads(stdout.decode("utf-8"))

    assert payload["status"] == "SUCCESS"
    assert payload["data"]["tasks"]


def test_cli_task_show_handles_arabic_payload(
    tmp_path,
):
    repository_root = Path(__file__).resolve().parents[2]
    project_root = tmp_path / "task-show-project"
    source_path = tmp_path / "source.txt"

    source_path.write_text(
        "وقع الحدث سنة 1945 وانتهت المرحلة لاحقاً.",
        encoding="utf-8",
    )

    _prepare_project(
        repository_root,
        project_root,
        source_path,
    )

    tasks_result = _run_cli(
        [
            "--json",
            "research",
            "tasks",
            "--project-root",
            str(project_root),
        ],
        cwd=repository_root,
    )

    tasks_payload = json.loads(tasks_result.stdout)
    task_id = tasks_payload["data"]["tasks"][0]["task_id"]

    show_result = _run_cli(
        [
            "--json",
            "research",
            "task-show",
            "--project-root",
            str(project_root),
            "--task-id",
            task_id,
        ],
        cwd=repository_root,
    )

    assert show_result.returncode == 0
    assert show_result.stderr == ""

    payload = json.loads(show_result.stdout)

    assert payload["data"]["task"]["task_id"] == task_id
    assert payload["data"]["queries"]


def test_cli_supports_paths_containing_spaces(
    tmp_path,
):
    repository_root = Path(__file__).resolve().parents[2]
    project_root = tmp_path / "project with spaces"
    source_path = tmp_path / "source with spaces.txt"

    source_path.write_text(
        "تأسست المؤسسة سنة 1980 وبدأ نشاطها.",
        encoding="utf-8",
    )

    _prepare_project(
        repository_root,
        project_root,
        source_path,
    )

    result = _run_cli(
        [
            "--json",
            "research",
            "verify",
            "--project-root",
            str(project_root),
        ],
        cwd=repository_root,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["status"] == "VALID"


def test_cli_json_has_no_traceback_on_normal_success(
    tmp_path,
):
    repository_root = Path(__file__).resolve().parents[2]
    project_root = tmp_path / "no-traceback"
    source_path = tmp_path / "source.txt"

    source_path.write_text(
        "تأسست المدينة سنة 1901 وبدأ نموها سريعاً.",
        encoding="utf-8",
    )

    _prepare_project(
        repository_root,
        project_root,
        source_path,
    )

    result = _run_cli(
        [
            "--json",
            "research",
            "status",
            "--project-root",
            str(project_root),
        ],
        cwd=repository_root,
    )

    assert result.returncode == 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
    json.loads(result.stdout)
