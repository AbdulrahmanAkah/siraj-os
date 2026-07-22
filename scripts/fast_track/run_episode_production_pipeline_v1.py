"""Explicit CLI for the offline-safe Episode Production Pipeline composition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from src.application.episode_orchestration_v1.runtime import load_episode_definition
from src.application.episode_production_v1.composition import EpisodeProductionComposition, load_pipeline_config


MODES = ("plan", "status", "run-next", "run-through", "resume", "run-stage")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compose and run a guarded SIRAJ episode pipeline.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--episode-definition", required=True)
    parser.add_argument("--pipeline-config", required=True)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--stage")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    return parser


def _exit_code(result: dict[str, object]) -> int:
    status = str(result.get("status") or result.get("manifest", {}).get("status", "UNKNOWN"))
    return 1 if status == "FAILED" else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "run-stage" and not args.stage:
        raise SystemExit("--stage is required for run-stage")
    if args.allow_external != args.confirm_live:
        raise SystemExit("--allow-external and --confirm-live must be supplied together")
    try:
        definition = load_episode_definition(Path(args.episode_definition))
        config = load_pipeline_config(Path(args.pipeline_config))
        pipeline = EpisodeProductionComposition(Path(args.project_root), definition, config, output_root=Path(args.output) if args.output else None)
        result = pipeline.build().execute(mode=args.mode, stage_id=args.stage, allow_external=args.allow_external, confirm_live=args.confirm_live, dry_run=args.dry_run)
    except (OSError, ValueError) as error:
        result = {"status": "FAILED", "error": str(error)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    else:
        status = str(result.get("status") or result.get("manifest", {}).get("status", "UNKNOWN"))
        print("FAIL: " + str(result.get("error") or "PERMANENT_FAILURE") if status == "FAILED" else "SUCCESS: " + status)
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
