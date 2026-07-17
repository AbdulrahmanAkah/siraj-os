from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _active_python() -> Path:
    explicit_python = os.environ.get(
        "SIRAJ_TEST_HOST_PYTHON",
        "",
    ).strip()

    if explicit_python:
        candidate = Path(explicit_python)

        if not candidate.is_file():
            raise RuntimeError(
                f"SIRAJ_TEST_HOST_PYTHON_NOT_FOUND:{candidate}"
            )

        return candidate

    return Path(sys.executable).resolve()


BUILD_PYTHON = _active_python()



ARABIC_TOPIC = (
    "\u0627\u062e\u062a\u0628\u0627\u0631 "
    "\u0627\u0644\u0625\u0637\u0644\u0627\u0642"
)

ARABIC_SOURCE = (
    "\u062a\u0623\u0633\u0633\u062a "
    "\u0627\u0644\u0645\u062f\u064a\u0646\u0629 "
    "\u0633\u0646\u0629 1901 "
    "\u0648\u0628\u062f\u0623 "
    "\u0646\u0645\u0648\u0647\u0627 "
    "\u0633\u0631\u064a\u0639\u0627\u064b."
)


def _utf8_environment() -> dict[str, str]:
    env = os.environ.copy()
    # A test runner may inject the source checkout through PYTHONPATH.  That
    # makes pip treat the adjacent ``siraj_os.egg-info`` as an already
    # installed distribution, bypassing wheel installation and launcher
    # generation.  Packaging subprocesses must exercise the wheel in the
    # isolated environment instead of inheriting source-tree imports.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONLEGACYWINDOWSSTDIO": "0",
        }
    )
    return env


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=_utf8_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=timeout,
        check=False,
    )


def _json_output(
    result: subprocess.CompletedProcess[str],
) -> dict:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            "CLI did not return valid JSON.\n"
            f"returncode={result.returncode}\n"
            f"stdout={result.stdout!r}\n"
            f"stderr={result.stderr!r}"
        ) from error


def _venv_python(venv_root: Path) -> Path:
    if os.name == "nt":
        return venv_root / "Scripts" / "python.exe"

    return venv_root / "bin" / "python"


def _venv_siraj(venv_root: Path) -> Path:
    if os.name == "nt":
        return venv_root / "Scripts" / "siraj.exe"

    return venv_root / "bin" / "siraj"


@pytest.fixture(scope="session")
def built_wheel(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    wheel_root = tmp_path_factory.mktemp("siraj-wheel")

    result = _run(
        [
            str(BUILD_PYTHON),
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_root),
        ],
        cwd=REPOSITORY_ROOT,
        timeout=180,
    )

    assert result.returncode == 0, (
        "Wheel build failed.\n"
        f"stdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )

    wheels = sorted(wheel_root.glob("*.whl"))

    assert len(wheels) == 1, (
        f"Expected exactly one wheel, found: {wheels}"
    )

    return wheels[0]


@pytest.fixture(scope="session")
def installed_release(
    tmp_path_factory: pytest.TempPathFactory,
    built_wheel: Path,
) -> dict[str, Path]:
    venv_root = tmp_path_factory.mktemp("siraj-clean-venv")

    create_result = _run(
        [
            str(BUILD_PYTHON),
            "-m",
            "venv",
            str(venv_root),
        ],
        cwd=REPOSITORY_ROOT,
        timeout=180,
    )

    assert create_result.returncode == 0, (
        "Clean venv creation failed.\n"
        f"stdout={create_result.stdout}\n"
        f"stderr={create_result.stderr}"
    )

    python_path = _venv_python(venv_root)

    install_result = _run(
        [
            str(python_path),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            str(built_wheel),
        ],
        cwd=REPOSITORY_ROOT,
        timeout=180,
    )

    assert install_result.returncode == 0, (
        "Wheel installation failed.\n"
        f"stdout={install_result.stdout}\n"
        f"stderr={install_result.stderr}"
    )

    siraj_path = _venv_siraj(venv_root)

    assert python_path.is_file()
    assert siraj_path.is_file()

    return {
        "venv": venv_root,
        "python": python_path,
        "siraj": siraj_path,
        "wheel": built_wheel,
    }


def _run_installed(
    installed_release: dict[str, Path],
    arguments: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            str(installed_release["siraj"]),
            *arguments,
        ],
        cwd=cwd,
        timeout=120,
    )


def _assert_success(
    result: subprocess.CompletedProcess[str],
) -> dict:
    payload = _json_output(result)

    assert result.returncode == 0, (
        f"stdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )
    assert payload["status"] == "SUCCESS"
    assert payload["exit_code"] == 0

    return payload


def _prepare_release_project(
    installed_release: dict[str, Path],
    workspace: Path,
    *,
    include_research_plan: bool = True,
) -> Path:
    project_root = workspace / "project with spaces"
    source_path = workspace / "source with spaces.txt"

    workspace.mkdir(parents=True, exist_ok=True)
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
            "release-hardening",
            "--topic",
            ARABIC_TOPIC,
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
            "Arabic release source",
            "--language",
            "ar",
            "--classification",
            "PUBLIC",
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

    if include_research_plan:
        commands.append(
            [
                "--json",
                "project",
                "plan-research",
                "--root",
                str(project_root),
            ]
        )

    for command in commands:
        result = _run_installed(
            installed_release,
            command,
            cwd=workspace,
        )
        _assert_success(result)

    return project_root


def test_wheel_contains_release_runtime_modules(
    built_wheel: Path,
):
    with zipfile.ZipFile(built_wheel) as archive:
        names = set(archive.namelist())

    required_suffixes = {
        "src/application/cli_v2.py",
        "src/application/project_runtime/runtime.py",
        "src/application/project_ingestion_runtime/runtime.py",
        "src/application/project_knowledge_runtime/runtime.py",
        "src/application/project_assessment_runtime/runtime.py",
        (
            "src/application/"
            "project_research_planning_runtime/runtime.py"
        ),
    }

    missing = {
        suffix
        for suffix in required_suffixes
        if not any(
            name.endswith(suffix)
            for name in names
        )
    }

    assert not missing, (
        f"Wheel is missing runtime files: {sorted(missing)}"
    )


def test_clean_venv_installed_cli_help(
    installed_release: dict[str, Path],
    tmp_path: Path,
):
    result = _run_installed(
        installed_release,
        ["--help"],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_clean_venv_imports_installed_package(
    installed_release: dict[str, Path],
    tmp_path: Path,
):
    result = _run(
        [
            str(installed_release["python"]),
            "-c",
            (
                "import inspect;"
                "import src.application.cli_v2 as cli;"
                "assert hasattr(cli,'main');"
                "print(inspect.getfile(cli))"
            ),
        ],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert "site-packages" in result.stdout.casefold()
    assert str(REPOSITORY_ROOT).casefold() not in (
        result.stdout.casefold()
    )


def test_installed_wheel_runs_complete_pipeline(
    installed_release: dict[str, Path],
    tmp_path: Path,
):
    workspace = tmp_path / "installed release workspace"

    project_root = _prepare_release_project(
        installed_release,
        workspace,
    )

    verification_commands = [
        [
            "--json",
            "project",
            "verify",
            "--root",
            str(project_root),
        ],
        [
            "--json",
            "knowledge",
            "verify",
            "--project-root",
            str(project_root),
        ],
        [
            "--json",
            "assessment",
            "verify",
            "--project-root",
            str(project_root),
        ],
        [
            "--json",
            "research",
            "verify",
            "--project-root",
            str(project_root),
        ],
    ]

    for command in verification_commands:
        result = _run_installed(
            installed_release,
            command,
            cwd=workspace,
        )
        payload = _assert_success(result)
        assert payload["data"]["status"] == "VALID"


def test_installed_cli_preserves_unicode_json(
    installed_release: dict[str, Path],
    tmp_path: Path,
):
    workspace = tmp_path / "unicode workspace"

    project_root = _prepare_release_project(
        installed_release,
        workspace,
    )

    result = _run_installed(
        installed_release,
        [
            "--json",
            "research",
            "tasks",
            "--project-root",
            str(project_root),
        ],
        cwd=workspace,
    )

    payload = _assert_success(result)
    objective = payload["data"]["tasks"][0]["objective"]

    assert "\u062a\u0623\u0633\u0633\u062a" in objective

    for marker in ("╪", "┘", "┌", "├", "┤"):
        assert marker not in objective


def test_research_status_is_not_run_for_legacy_project(
    installed_release: dict[str, Path],
    tmp_path: Path,
):
    workspace = tmp_path / "legacy workspace"

    project_root = _prepare_release_project(
        installed_release,
        workspace,
        include_research_plan=False,
    )

    result = _run_installed(
        installed_release,
        [
            "--json",
            "research",
            "status",
            "--project-root",
            str(project_root),
        ],
        cwd=workspace,
    )

    payload = _json_output(result)

    assert payload["status"] == "BLOCKED"
    assert payload["data"]["status"] == "NOT_RUN"
    assert "Traceback" not in result.stderr


def test_corrupted_research_result_is_reported_without_traceback(
    installed_release: dict[str, Path],
    tmp_path: Path,
):
    workspace = tmp_path / "corruption workspace"

    project_root = _prepare_release_project(
        installed_release,
        workspace,
    )

    result_path = (
        project_root
        / "working"
        / "research"
        / "research-result.json"
    )

    result_path.write_text(
        '{"schema_version":',
        encoding="utf-8",
    )

    result = _run_installed(
        installed_release,
        [
            "--json",
            "research",
            "verify",
            "--project-root",
            str(project_root),
        ],
        cwd=workspace,
    )

    payload = _json_output(result)

    assert result.returncode != 0
    assert payload["status"] == "VALIDATION_FAILURE"
    assert payload["data"]["status"] == "INVALID"

    issue_codes = {
        item["code"]
        for item in payload["data"]["issues"]
    }

    assert "RESEARCH_ARTIFACT_INVALID" in issue_codes
    assert "Traceback" not in result.stderr


def test_missing_research_artifact_is_reported_without_traceback(
    installed_release: dict[str, Path],
    tmp_path: Path,
):
    workspace = tmp_path / "missing artifact workspace"

    project_root = _prepare_release_project(
        installed_release,
        workspace,
    )

    tasks_path = (
        project_root
        / "working"
        / "research"
        / "research-tasks.json"
    )
    tasks_path.unlink()

    result = _run_installed(
        installed_release,
        [
            "--json",
            "research",
            "verify",
            "--project-root",
            str(project_root),
        ],
        cwd=workspace,
    )

    payload = _json_output(result)

    assert result.returncode != 0
    assert payload["status"] == "VALIDATION_FAILURE"
    assert payload["data"]["status"] == "INVALID"

    issue_codes = {
        item["code"]
        for item in payload["data"]["issues"]
    }

    assert "RESEARCH_ARTIFACT_INVALID" in issue_codes
    assert "Traceback" not in result.stderr


def test_reinstalled_wheel_does_not_require_repository_cwd(
    installed_release: dict[str, Path],
    tmp_path: Path,
):
    external_cwd = tmp_path / "outside repository"
    external_cwd.mkdir(parents=True)

    result = _run_installed(
        installed_release,
        ["--json", "health"],
        cwd=external_cwd,
    )

    payload = _assert_success(result)

    assert payload["command"] == "health"
    assert str(REPOSITORY_ROOT).casefold() not in (
        result.stderr.casefold()
    )
