from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from scripts.project_progress.recorder import (
    record_milestone,
)


PROGRESS_FILES = {
    "PROJECT_PROGRESS.md",
    "docs/execution/project-milestones.json",
}

MAJOR_PREFIXES = (
    "src/",
    "projects/",
    "scripts/fast_track/",
    "scripts/shamela/",
    "scripts/project_progress/",
    "docs/execution/",
)


def git_output(*arguments: str) -> str:
    process = subprocess.run(
        ["git", *arguments],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if process.returncode != 0:
        raise RuntimeError(
            process.stderr.strip()
            or "GIT_COMMAND_FAILED"
        )

    return process.stdout


def main() -> int:
    staged = [
        line.strip()
        for line in git_output(
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
        ).splitlines()
        if line.strip()
    ]

    major_files = [
        path
        for path in staged
        if path not in PROGRESS_FILES
        and path.startswith(MAJOR_PREFIXES)
    ]

    if not major_files:
        return 0

    if PROGRESS_FILES.intersection(staged):
        return 0

    staged_diff = git_output(
        "diff",
        "--cached",
        "--binary",
    )

    digest = hashlib.sha256(
        staged_diff.encode("utf-8")
    ).hexdigest()[:16]

    record_milestone(
        project_progress_path=(
            REPO / "PROJECT_PROGRESS.md"
        ),
        ledger_path=(
            REPO
            / "docs"
            / "execution"
            / "project-milestones.json"
        ),
        milestone_id=f"auto-commit-{digest}",
        title_ar=(
            "تحديث تنفيذي آلي قبل Commit رئيسي"
        ),
        status="AUTO_RECORDED",
        summary_ar=(
            "اكتشف Git hook تغييرات كبيرة لم يصاحبها تحديث "
            "يدوي لسجل المشروع، فأضاف هذا السجل تلقائيًا. "
            "الملفات المتأثرة: "
            + "، ".join(major_files[:20])
        ),
        next_action_ar=(
            "مراجعة وصف milestone وتحديثه بتفاصيل دلالية أدق "
            "عند تقييم نتيجة المرحلة."
        ),
        recorded_at=datetime.now(
            timezone.utc
        ).isoformat(),
        changed_files=major_files,
        metadata={
            "automatic_git_hook": True,
            "staged_file_count": len(major_files),
        },
    )

    add = subprocess.run(
        [
            "git",
            "add",
            "--",
            "PROJECT_PROGRESS.md",
            "docs/execution/project-milestones.json",
        ],
        cwd=REPO,
        check=False,
    )

    if add.returncode != 0:
        raise RuntimeError(
            "PROGRESS_FILES_GIT_ADD_FAILED"
        )

    print(
        "SIRAJ_PROJECT_PROGRESS_AUTO_UPDATED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
