from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.quran_source_binding import (
        build_and_write,
    )

    outputs = build_and_write(repo, args.output_root.resolve())
    source = json.loads(
        outputs["source_materialization"].read_text(encoding="utf-8-sig")
    )
    binding = json.loads(
        outputs["binding_candidate"].read_text(encoding="utf-8-sig")
    )
    print("STATUS=PASS_ADAM_QURAN_SOURCE_BINDING_BATCH")
    print(f"SOURCE_PACKAGE_ID={source['source_package_id']}")
    print(f"BINDING_CANDIDATE_ID={binding['binding_candidate_id']}")
    print(f"QURAN_SOURCE_RECORDS={source['source_record_count']}")
    print(f"QURAN_EXPLICIT_EVENTS={binding['event_count']}")
    print("HUMAN_APPROVAL=PENDING")
    print("FULL_EPISODE_ADJUDICATION_COMPLETE=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    for name, path in outputs.items():
        print(f"{name.upper()}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
