from __future__ import annotations

import unittest

from scripts.project_progress.pre_commit_progress_guard import (
    ProjectProgressGuardError,
    validate_staged_paths,
)


class ProjectProgressGuardTests(unittest.TestCase):
    def test_empty_staging_is_allowed(self) -> None:
        validate_staged_paths([])

    def test_progress_only_commit_is_allowed(self) -> None:
        validate_staged_paths(["PROJECT_PROGRESS.md"])

    def test_repository_change_with_progress_is_allowed(self) -> None:
        validate_staged_paths(
            ["src/example.py", "tests/test_example.py", "PROJECT_PROGRESS.md"]
        )

    def test_repository_change_without_progress_is_blocked(self) -> None:
        with self.assertRaises(ProjectProgressGuardError):
            validate_staged_paths(["src/example.py"])

    def test_windows_paths_are_normalized(self) -> None:
        validate_staged_paths(
            [r"src\application\example.py", r"PROJECT_PROGRESS.md"]
        )


if __name__ == "__main__":
    unittest.main()
