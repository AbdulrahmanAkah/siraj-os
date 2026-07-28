from __future__ import annotations
import argparse
import json
import sys
import zipfile
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--no-local-scan", action="store_true")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))
    from src.application.storyboard_runtime.full_episode_adjudication_inventory import (
        build_inventory, write_outputs,
    )
    project = repo / "projects/episode-001-adam"
    inventory = build_inventory(
        event_map_path=project / "editorial/event-map.json",
        project_root=project,
        source_classification_path=project / "evidence/source-origin-classification-v1.json",
        human_approval_path=project / "evidence/gap-human-approval-v1.json",
        include_local_scan=not args.no_local_scan,
    )
    output = args.output_root.resolve()
    outputs = write_outputs(output, inventory)
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in outputs.values():
            zf.write(path, path.name)
    print("STATUS=PASS_FULL_EPISODE_ADJUDICATION_INVENTORY")
    print(f"INVENTORY_ID={inventory['inventory_id']}")
    print(f"EVENT_COUNT={inventory['event_count']}")
    print(f"HUMAN_DECISIONS_RECORDED={inventory['coverage']['human_decision_recorded_events']}")
    print(f"EVENTS_WITH_CLASSIFIED_SOURCES={inventory['coverage']['events_with_classified_source_records']}")
    print(f"EVENTS_WITH_LOCAL_ARTIFACT_MENTIONS={inventory['coverage']['events_with_local_artifact_mentions']}")
    print(f"FILES_SCANNED={inventory['scan_summary']['files_scanned']}")
    print(f"NEXT_BATCH_ITEMS={len(inventory['recommended_next_batch'])}")
    print("FULL_EPISODE_ADJUDICATION_COMPLETE=NO")
    print("APPROVED_EVIDENCE_PACKAGE_COMPLETE=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(f"OUTPUT_ROOT={output}")
    print(f"ARCHIVE={archive}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
