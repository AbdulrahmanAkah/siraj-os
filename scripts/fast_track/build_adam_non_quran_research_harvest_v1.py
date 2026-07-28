from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--backlog-only", action="store_true")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.non_quran_research_harvest import (
        build_harvest,
        write_local_outputs,
    )

    inventory = (
        repo
        / "projects/episode-001-adam/evidence/"
        "full-episode-adjudication-inventory-v1.json"
    )
    project = repo / "projects/episode-001-adam"
    harvest, backlog, prompts, editorial, manifest = build_harvest(
        inventory_path=inventory,
        project_root=project,
        include_snippets=not args.backlog_only,
    )
    outputs = write_local_outputs(
        output_root=args.output_root.resolve(),
        harvest=harvest,
        backlog=backlog,
        prompt_pack=prompts,
        editorial=editorial,
        manifest=manifest,
    )
    print("STATUS=PASS_ADAM_NON_QURAN_RESEARCH_HARVEST")
    print(f"HARVEST_ID={harvest['harvest_id']}")
    print(f"FACTUAL_EVENTS={harvest['factual_event_count']}")
    print(f"EDITORIAL_EVENTS={harvest['editorial_event_count']}")
    print(f"EVENTS_WITH_CANDIDATES={harvest['events_with_candidates']}")
    print(f"DEDUPLICATED_CANDIDATES={harvest['candidate_count']}")
    print(f"FILES_SCANNED={harvest['scan_summary']['files_scanned']}")
    print("HUMAN_APPROVAL=PENDING")
    print("FULL_EPISODE_ADJUDICATION_COMPLETE=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
