from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.storyboard_runtime.preliminary_style_frame_reference_binding_v1 import (  # noqa: E402
    OPERATIONAL_NEXT_STAGE,
    build_all,
    read_json,
    write_json,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--materialize-project-files", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    episode = repo / "projects/episode-001-adam"
    cinematic = episode / "cinematic"
    evidence = episode / "evidence"
    contracts = episode / "contracts"
    asset_root = cinematic / "preliminary-style-frame-reference-set-v1/assets"

    definition = read_json(contracts / "episode-definition-v1.json")
    brief = read_json(cinematic / "prestige-production-brief-v2-1.json")
    (
        reference_set,
        policy,
        approval,
        receipt,
        binding,
        motion_gate,
        updated_definition,
        updated_brief,
        markdown,
    ) = build_all(
        asset_root=asset_root,
        episode_definition=definition,
        production_brief=brief,
    )

    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        reference_set=reference_set,
        policy=policy,
        approval=approval,
        receipt=receipt,
        binding=binding,
        gate=motion_gate,
        episode_definition=updated_definition,
        production_brief=updated_brief,
        markdown=markdown,
    )

    if args.materialize_project_files:
        write_json(cinematic / "preliminary-style-frame-reference-set-v1.json", reference_set)
        write_json(cinematic / "preliminary-style-frame-visual-safety-policy-v1.json", policy)
        write_json(evidence / "preliminary-style-frame-human-approval-v1.json", approval)
        write_json(evidence / "preliminary-style-frame-human-approval-receipt-v1.json", receipt)
        write_json(contracts / "preliminary-style-frame-human-approval-binding-v1.json", binding)
        write_json(cinematic / "non-paid-single-shot-motion-prototype-gate-v1.json", motion_gate)
        write_json(contracts / "episode-definition-v1.json", updated_definition)
        write_json(cinematic / "prestige-production-brief-v2-1.json", updated_brief)
        (cinematic / "preliminary-style-frame-human-approval-v1.md").write_text(
            markdown, encoding="utf-8", newline="\n"
        )

    print("STATUS=PASS_ADAM_PRELIMINARY_STYLE_FRAME_REFERENCE_BINDING_AND_MOTION_GATE_V1")
    print("CANONICAL_TIMEZONE=Asia/Baghdad")
    print("REFERENCE_ASSET_COUNT=8")
    print("PRELIMINARY_STYLE_FRAME_HUMAN_APPROVAL=YES")
    print("STORYBOARD_FINAL_SHOT_BINDING=NO")
    print("MASTER_VISUAL_APPROVAL=NO")
    print("FINAL_MASTER_VISUAL_APPROVAL=NO")
    print("MOTION_PROTOTYPE_AUTHORISATION=AUTHORISED_SINGLE_NON_PAID_ENVIRONMENT_SHOT_ONLY")
    print("MOTION_SOURCE_ASSET_ID=ADAM-PREF-001")
    print("MOTION_DURATION_WINDOW_SECONDS=8-12")
    print("MOTION_OUTPUT_COUNT_LIMIT=1")
    print("AUDIO_GENERATION=BLOCKED")
    print("FULL_EPISODE_VIDEO_GENERATION=BLOCKED")
    print("LIVE_EXECUTION_STATUS=BLOCKED")
    print("PAID_EXECUTION=BLOCKED")
    print("DIRECT_EXECUTION=BLOCKED")
    print("RUNWARE_EXECUTION=BLOCKED")
    print(f"REFERENCE_SET_ID={reference_set['reference_set_id']}")
    print(f"VISUAL_SAFETY_POLICY_ID={policy['policy_id']}")
    print(f"APPROVAL_ID={approval['approval_id']}")
    print(f"APPROVAL_RECEIPT_ID={receipt['receipt_id']}")
    print(f"APPROVAL_BINDING_ID={binding['binding_id']}")
    print(f"MOTION_GATE_ID={motion_gate['gate_id']}")
    print(f"OPERATIONAL_NEXT_STAGE={OPERATIONAL_NEXT_STAGE}")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
