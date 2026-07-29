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

    from src.application.storyboard_runtime.master_visual_development_v1 import (
        build_all,
        read_json,
        write_json,
        write_outputs,
    )

    episode = repo / "projects/episode-001-adam"
    cinematic = episode / "cinematic"
    evidence = episode / "evidence"
    contracts = episode / "contracts"

    storyboard = read_json(cinematic / "detailed-storyboard-v2-1.json")
    approval = read_json(
        evidence / "final-storyboard-master-human-approval-v2-1.json"
    )
    approval_binding = read_json(
        contracts / "final-storyboard-master-approval-binding-v2-1.json"
    )
    visual_gate = read_json(cinematic / "non-paid-visual-development-gate-v1.json")
    definition = read_json(contracts / "episode-definition-v1.json")
    brief = read_json(cinematic / "prestige-production-brief-v2-1.json")

    (
        visual_bible,
        color_script,
        animatic,
        audit,
        binding,
        updated_definition,
        updated_brief,
    ) = build_all(
        storyboard=storyboard,
        approval=approval,
        approval_binding=approval_binding,
        visual_gate=visual_gate,
        episode_definition=definition,
        production_brief=brief,
    )

    project_outputs = {
        cinematic / "master-visual-bible-v1.json": visual_bible,
        cinematic / "color-script-v1.json": color_script,
        cinematic / "non-paid-animatic-development-v1.json": animatic,
        cinematic / "master-visual-development-audit-v1.json": audit,
        contracts / "master-visual-development-binding-v1.json": binding,
        contracts / "episode-definition-v1.json": updated_definition,
        cinematic / "prestige-production-brief-v2-1.json": updated_brief,
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
                "Tracked master-visual development files differ: "
                + ", ".join(different)
            )

    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
        audit=audit,
        binding=binding,
        episode_definition=updated_definition,
        production_brief=updated_brief,
    )

    print("STATUS=PASS_ADAM_MASTER_VISUAL_DEVELOPMENT_V1")
    print("CANONICAL_TIMEZONE=Asia/Baghdad")
    print("DIRECTORS_CUT_VERSION=2.1")
    print("MASTER_VISUAL_BIBLE_STATUS=DEVELOPED_AWAITING_HUMAN_APPROVAL")
    print("COLOR_SCRIPT_STATUS=COMPLETE_NON_PAID_DEVELOPMENT_AWAITING_HUMAN_APPROVAL")
    print("NON_PAID_ANIMATIC_STATUS=PLANNED_NON_PAID_NO_MEDIA_EXECUTION")
    print("SEQUENCE_COVERAGE=14/14")
    print("SHOT_COVERAGE=70/70")
    print("EPISODE_DURATION_SECONDS=1320")
    print("MEDIA_ASSETS_CREATED=0")
    print("MASTER_VISUAL_APPROVAL=NO")
    print("LIVE_EXECUTION_STATUS=BLOCKED")
    print("PAID_EXECUTION=BLOCKED")
    print("DIRECT_EXECUTION=BLOCKED")
    print("RUNWARE_EXECUTION=BLOCKED")
    print("GENERATED_VIDEO_PLANNED_SECONDS=0")
    print(f"VISUAL_BIBLE_ID={visual_bible['visual_bible_id']}")
    print(f"COLOR_SCRIPT_ID={color_script['color_script_id']}")
    print(f"ANIMATIC_DEVELOPMENT_ID={animatic['animatic_development_id']}")
    print(f"DEVELOPMENT_AUDIT_ID={audit['audit_id']}")
    print(f"DEVELOPMENT_BINDING_ID={binding['binding_id']}")
    print(f"NEXT_STAGE={updated_definition['next_stage']}")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
