"""Build the local publication package through the canonical composition root."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from src.application.episode_orchestration_v1.runtime import load_episode_definition
from src.application.episode_production_v1.composition import EpisodeProductionComposition, load_pipeline_config
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", required=True); parser.add_argument("--episode-definition", required=True); parser.add_argument("--pipeline-config", required=True); parser.add_argument("--output", required=True); parser.add_argument("--mode", choices=("plan", "run"), default="plan"); parser.add_argument("--json", action="store_true"); args = parser.parse_args(argv)
    root = Path(args.project_root).resolve(); definition = load_episode_definition(Path(args.episode_definition)); config = load_pipeline_config(Path(args.pipeline_config)); orchestrator = EpisodeProductionComposition(root, definition, config, output_root=Path(args.output)).build()
    result = orchestrator.execute(mode="plan" if args.mode == "plan" else "run-stage", stage_id="publication_package")
    payload = {"status": result.get("status", result.get("plan", {}).get("requested_mode", "PLAN")), "result": result, "upload_performed": False, "network": False}
    print(json.dumps(payload, ensure_ascii=False) if args.json else payload["status"]); return 0 if payload["status"] not in {"FAILED"} else 2
if __name__ == "__main__": raise SystemExit(main())
