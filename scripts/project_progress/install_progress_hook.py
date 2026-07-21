from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
MARKER = "SIRAJ_PROJECT_PROGRESS_HOOK_V1"


def main() -> int:
    process = subprocess.run(
        [
            "git",
            "rev-parse",
            "--git-dir",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if process.returncode != 0:
        raise RuntimeError(
            "GIT_DIRECTORY_NOT_FOUND"
        )

    git_dir = Path(
        process.stdout.strip()
    )

    if not git_dir.is_absolute():
        git_dir = REPO / git_dir

    hook_path = git_dir / "hooks" / "pre-commit"
    hook_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    previous_hook = None

    if hook_path.is_file():
        existing = hook_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if MARKER not in existing:
            timestamp = datetime.now().strftime(
                "%Y%m%d-%H%M%S"
            )

            previous_hook = (
                hook_path.parent
                / f"pre-commit.siraj-backup-{timestamp}"
            )

            previous_hook.write_bytes(
                hook_path.read_bytes()
            )

    python_path = Path(sys.executable)
    guard_path = (
        REPO
        / "scripts"
        / "project_progress"
        / "pre_commit_progress_guard.py"
    )

    lines = [
        "#!/bin/sh",
        f"# {MARKER}",
        "set -e",
    ]

    if previous_hook:
        lines.append(
            f'"{previous_hook.as_posix()}" "$@"'
        )

    lines.append(
        f'exec "{python_path.as_posix()}" '
        f'"{guard_path.as_posix()}" "$@"'
    )

    hook_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    try:
        os.chmod(hook_path, 0o755)
    except OSError:
        pass

    print(str(hook_path))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
