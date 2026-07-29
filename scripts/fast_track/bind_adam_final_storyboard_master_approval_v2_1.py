from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def json_equal(path: Path, expected: dict) -> bool:
    if not path.is_file():
        return False
    return json.loads(path.read_text(encoding="utf-8-sig")) == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--materialize-project-files", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.final_storyboard_master_approval_binding_v2_1 import (
        build_all,
        read_json,
        write_json,
        write_outputs,
    )

    episode = repo / "projects/episode-001-adam"
    editorial = episode / "editorial"
    cinematic = episode / "cinematic"
    evidence = episode / "evidence"
    contracts = episode / "contracts"

    script = read_json(editorial / "prestige-cinematic-script-v2-1.json")
    storyboard = read_json(cinematic / "detailed-storyboard-v2-1.json")
    trace = read_json(evidence / "script-storyboard-evidence-trace-v2-1.json")
    approval_request = read_json(
        evidence / "script-storyboard-human-approval-request-v2-1.json"
    )
    audit = read_json(
        cinematic / "storyboard-master-directorial-audit-v2-1.json"
    )
    definition = read_json(contracts / "episode-definition-v1.json")

    approval, receipt, binding, visual_gate, updated = build_all(
        script=script,
        storyboard=storyboard,
        trace=trace,
        approval_request=approval_request,
        audit=audit,
        episode_definition=definition,
    )

    project_outputs = {
        evidence / "final-storyboard-master-human-approval-v2-1.json":
            approval,
        evidence / "final-storyboard-master-approval-receipt-v2-1.json":
            receipt,
        contracts / "final-storyboard-master-approval-binding-v2-1.json":
            binding,
        cinematic / "non-paid-visual-development-gate-v1.json":
            visual_gate,
        contracts / "episode-definition-v1.json": updated,
    }

    if args.materialize_project_files:
        for path, payload in project_outputs.items():
            write_json(path, payload)
    else:
        different = [
            str(path)
            for path, payload in project_outputs.items()
            if not json_equal(path, payload)
        ]
        if different:
            raise RuntimeError(
                "Tracked storyboard approval-binding files differ: "
                + ", ".join(different)
            )

    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        approval=approval,
        receipt=receipt,
        binding=binding,
        visual_gate=visual_gate,
        episode_definition=updated,
    )

    print("STATUS=PASS_ADAM_FINAL_STORYBOARD_MASTER_APPROVAL_BINDING_V2_1")
    print("CANONICAL_TIMEZONE=Asia/Baghdad")
    print("DIRECTORS_CUT_VERSION=2.1")
    print("HUMAN_SCRIPT_APPROVAL=YES")
    print("RELIGIOUS_SAFETY_APPROVAL=YES")
    print("HUMAN_STORYBOARD_APPROVAL=YES")
    print("STORYBOARD_COMPLETION_STATUS=COMPLETE_HUMAN_APPROVED")
    print("MASTER_VISUAL_APPROVAL=NO")
    print("NON_PAID_VISUAL_DEVELOPMENT_GATE=OPEN")
    print("LIVE_EXECUTION_STATUS=BLOCKED")
    print("PAID_EXECUTION=BLOCKED")
    print("DIRECT_EXECUTION=BLOCKED")
    print("RUNWARE_EXECUTION=BLOCKED")
    print("GENERATED_VIDEO_PLANNED_SECONDS=0")
    print(f"APPROVAL_ID={approval['approval_id']}")
    print(f"APPROVAL_RECEIPT_ID={receipt['receipt_id']}")
    print(f"APPROVAL_BINDING_ID={binding['binding_id']}")
    print(f"VISUAL_DEVELOPMENT_GATE_ID={visual_gate['gate_id']}")
    print(f"SCRIPT_ID={binding['script_id']}")
    print(f"SCRIPT_FINGERPRINT={binding['script_fingerprint']}")
    print(f"STORYBOARD_ID={binding['storyboard_id']}")
    print(f"STORYBOARD_FINGERPRINT={binding['storyboard_fingerprint']}")
    print(
        "NEXT_STAGE="
        "MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_NON_PAID_ANIMATIC_DEVELOPMENT"
    )
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
