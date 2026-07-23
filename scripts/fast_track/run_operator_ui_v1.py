"""Start the local-only operator UI with an injected composition factory."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from src.application.episode_production_v1.composition import EpisodeProductionComposition, load_pipeline_config
from src.application.episode_orchestration_v1.runtime import load_episode_definition
from src.application.local_operator_ui_v1.runtime import LocalOperatorApplication, build_operator_server
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", required=True); parser.add_argument("--episode-definition", required=True); parser.add_argument("--pipeline-config", required=True); parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=8765); parser.add_argument("--plan-only", action="store_true"); args = parser.parse_args(argv)
    root = Path(args.project_root).resolve(); definition = load_episode_definition(Path(args.episode_definition)); config = load_pipeline_config(Path(args.pipeline_config))
    app = LocalOperatorApplication(root, lambda episode_id: EpisodeProductionComposition(root, definition, config, output_root=root / "working" / episode_id / "orchestrator").build())
    if args.plan_only:
        print(json.dumps({"status": "LOCAL_OPERATOR_UI_V1_IMPLEMENTED", "host": args.host, "port": args.port, "network": False}, ensure_ascii=False)); return 0
    build_operator_server(app, host=args.host, port=args.port, episode_ids=[definition["episode_id"]]).serve_forever(); return 0
if __name__ == "__main__": raise SystemExit(main())
