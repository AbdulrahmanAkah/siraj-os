"""Local CLI for Episode Orchestrator v1; it never enables providers by default."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from src.application.episode_orchestration_v1.runtime import EpisodeOrchestrator, VALID_MODES, load_episode_definition


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan and resume a SIRAJ documentary episode without hidden provider calls.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--episode-definition", required=True)
    parser.add_argument("--mode", required=True, choices=sorted(VALID_MODES))
    parser.add_argument("--stage")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    return parser


def _natural_message(result: dict[str, object]) -> str:
    status = str(result.get("status") or result.get("manifest", {}).get("status", "UNKNOWN"))
    if status in {"WAITING_FOR_EXTERNAL_PROVIDER", "WAITING_FOR_HUMAN_APPROVAL", "PARTIALLY_COMPLETED", "CREATED", "PLANNING"}:
        return f"BLOCKED_OR_WAITING: {status}"
    if status == "FAILED":
        return "FAIL: PERMANENT_FAILURE"
    return f"SUCCESS: {status}"


def exit_code_for_result(result: dict[str, object]) -> int:
    status = str(result.get("status") or result.get("manifest", {}).get("status", "UNKNOWN"))
    return 1 if status == "FAILED" else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode in {"run-stage", "invalidate-stage"} and not args.stage:
        raise SystemExit("--stage is required for this mode")
    if args.allow_external != args.confirm_live:
        raise SystemExit("--allow-external and --confirm-live must be supplied together")
    root = Path(args.project_root)
    definition = load_episode_definition(Path(args.episode_definition))
    orchestrator = EpisodeOrchestrator(root, definition, output_root=Path(args.output) if args.output else None)
    result = orchestrator.execute(mode=args.mode, stage_id=args.stage, allow_external=args.allow_external, confirm_live=args.confirm_live, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(_natural_message(result))
    return exit_code_for_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
