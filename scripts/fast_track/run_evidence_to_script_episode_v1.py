"""Local CLI for evidence-bound episode scripting; it never configures a model provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from src.application.episode_orchestration_v1.runtime import load_episode_definition
from src.application.evidence_to_script_episode_v1.runtime import EvidenceToScriptEpisodeAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate or plan evidence-bound episode scripting without provider calls.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--episode-definition", required=True)
    parser.add_argument("--evidence-package", required=True)
    parser.add_argument("--mode", required=True, choices=("validate-input", "plan", "generate", "verify", "status"))
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--confirm-live", action="store_true")
    return parser


def exit_code(result: dict[str, object]) -> int:
    return 0 if result.get("status") in {"READY", "PASS", "PASS_WITH_WARNINGS", "COMPLETED", "COMPLETED_WITH_WARNINGS", "DISCONNECTED"} else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.allow_external != args.confirm_live:
        raise SystemExit("--allow-external and --confirm-live must be supplied together")
    definition = load_episode_definition(Path(args.episode_definition))
    adapter = EvidenceToScriptEpisodeAdapter(Path(args.project_root), Path(args.evidence_package), output_root=Path(args.output) if args.output else None)
    if args.mode == "validate-input":
        _, errors = adapter.validate_input(definition)
        result: dict[str, object] = {"status": "PASS" if not errors else "VALIDATION_ERROR", "errors": errors}
    elif args.mode == "plan":
        result = adapter.plan(definition)
    elif args.mode == "generate":
        stage = adapter.execute(definition, "cli-local-run")
        result = {"status": stage.status, "errors": list(stage.errors), "blocker": stage.blocker, "next_action": stage.next_action}
    elif args.mode == "verify":
        result = adapter.verify(definition)
    else:
        result = adapter.status(definition)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    else:
        status = str(result.get("status", "UNKNOWN"))
        print(f"SUCCESS: {status}" if exit_code(result) == 0 else f"FAIL: {status}")
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
