from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.final_review_publish_package_v1 import (
    REQUIRED_CHECKLIST_KEYS,
    approve_final_review_and_build_publish_package,
    load_final_review_status,
    request_final_review_changes,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")

    approve = subparsers.add_parser("approve")
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--title", required=True)
    approve.add_argument("--description", default="")
    approve.add_argument("--tags", default="")
    approve.add_argument(
        "--visibility",
        choices=("PRIVATE", "UNLISTED", "PUBLIC"),
        default="PRIVATE",
    )
    approve.add_argument("--notes", default="")
    approve.add_argument("--confirm-all", action="store_true")

    changes = subparsers.add_parser("request-changes")
    changes.add_argument("--reviewer", required=True)
    changes.add_argument(
        "--category",
        action="append",
        required=True,
        choices=("VISUAL", "AUDIO", "CONTENT_ACCURACY", "METADATA", "OTHER"),
    )
    changes.add_argument("--notes", required=True)
    changes.add_argument("--shot-id", action="append", default=[])

    args = parser.parse_args()
    if args.command == "status":
        payload = load_final_review_status(args.repo_root)
    elif args.command == "approve":
        checklist = {
            key: bool(args.confirm_all)
            for key in REQUIRED_CHECKLIST_KEYS
        }
        result = approve_final_review_and_build_publish_package(
            args.repo_root,
            reviewer=args.reviewer,
            checklist=checklist,
            title=args.title,
            description=args.description,
            tags=args.tags,
            notes=args.notes,
            visibility_preference=args.visibility,
        )
        payload = {
            "episode_id": result.episode_id,
            "status": result.status,
            "decision": result.decision,
            "review_path": str(result.review_path),
            "publish_manifest_path": str(result.publish_manifest_path),
            "final_master_path": str(result.final_master_path),
        }
    else:
        result = request_final_review_changes(
            args.repo_root,
            reviewer=args.reviewer,
            categories=args.category,
            notes=args.notes,
            shot_ids=args.shot_id,
        )
        payload = {
            "episode_id": result.episode_id,
            "status": result.status,
            "decision": result.decision,
            "review_path": str(result.review_path),
            "repair_request_path": str(result.repair_request_path),
            "final_master_path": str(result.final_master_path),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
