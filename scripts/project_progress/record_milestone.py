from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from scripts.project_progress.recorder import (
    record_milestone,
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument(
        "--next-action",
        required=True,
    )
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
    )

    args = parser.parse_args()

    milestone = record_milestone(
        project_progress_path=(
            REPO / "PROJECT_PROGRESS.md"
        ),
        ledger_path=(
            REPO
            / "docs"
            / "execution"
            / "project-milestones.json"
        ),
        milestone_id=args.id,
        title_ar=args.title,
        status=args.status,
        summary_ar=args.summary,
        next_action_ar=args.next_action,
        changed_files=args.changed_file,
    )

    print(milestone["milestone_id"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
