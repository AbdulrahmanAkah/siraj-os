from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Iterable

PROGRESS_PATH = "PROJECT_PROGRESS.md"


class ProjectProgressGuardError(ValueError):
    pass


def normalize_paths(paths: Iterable[str]) -> list[str]:
    return sorted(
        {
            str(path).strip().replace("\\", "/")
            for path in paths
            if str(path).strip()
        }
    )


def validate_staged_paths(paths: Iterable[str]) -> None:
    staged = normalize_paths(paths)
    if not staged:
        return
    non_progress = [path for path in staged if path != PROGRESS_PATH]
    if non_progress and PROGRESS_PATH not in staged:
        raise ProjectProgressGuardError(
            "PROJECT_PROGRESS.md must be staged whenever repository changes are committed. "
            "Update the project progress record, stage it, and retry the commit."
        )


def discover_repo_root() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ProjectProgressGuardError(
            "Cannot determine repository root: " + completed.stderr.strip()
        )
    return Path(completed.stdout.strip()).resolve()


def read_staged_paths(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD"],
        cwd=str(repo_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ProjectProgressGuardError(
            "Cannot inspect staged paths: " + completed.stderr.strip()
        )
    return completed.stdout.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve() if args.repo_root else discover_repo_root()
    staged = read_staged_paths(repo_root)
    validate_staged_paths(staged)
    print("STATUS=PASS_PRE_COMMIT_PROJECT_PROGRESS_GUARD")
    print("STAGED_PATH_COUNT=" + str(len(normalize_paths(staged))))
    print("PROJECT_PROGRESS_STAGED=" + str(PROGRESS_PATH in normalize_paths(staged)).upper())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProjectProgressGuardError as exc:
        print("STATUS=FAIL_PRE_COMMIT_PROJECT_PROGRESS_GUARD")
        print(str(exc))
        raise SystemExit(1)
