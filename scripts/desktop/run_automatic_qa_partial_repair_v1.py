from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.automatic_qa_partial_repair_v1 import (
    run_automatic_qa_and_partial_repair,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run_automatic_qa_and_partial_repair(args.repo_root)
    print(
        json.dumps(
            {
                "status": result.status,
                "episode_id": result.episode_id,
                "blocking_issue_count": result.blocking_issue_count,
                "warning_count": result.warning_count,
                "repair_passes": result.repair_passes,
                "repaired_shot_count": result.repaired_shot_count,
                "reused_shot_count": result.reused_shot_count,
                "report_path": str(result.report_path),
                "final_master_path": str(result.final_master_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
