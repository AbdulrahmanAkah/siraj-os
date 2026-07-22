"""Offline source-package validation entry point; extraction remains injected."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from src.application.research_verification_episode_v1.runtime import validate_source_package

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", required=True); parser.add_argument("--source-package", required=True); parser.add_argument("--episode-id", required=True); parser.add_argument("--mode", choices=("validate-input", "plan", "status"), default="plan"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = Path(args.project_root).resolve(); value = json.loads(Path(args.source_package).read_text(encoding="utf-8-sig")); errors = validate_source_package(value, project_root=root, episode_id=args.episode_id)
        result = {"status": "PASS" if not errors else "FAIL", "mode": args.mode, "extractor": "IMPLEMENTED_EXTRACTOR_DISCONNECTED", "errors": errors, "network": False}
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {"status": "FAIL", "errors": [type(error).__name__], "network": False}
    print(json.dumps(result, ensure_ascii=False) if args.json else result["status"])
    return 0 if result["status"] == "PASS" else 2
if __name__ == "__main__": raise SystemExit(main())
