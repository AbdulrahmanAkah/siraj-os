from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def json_equal(path: Path, expected: dict) -> bool:
    if not path.is_file():
        return False
    return json.loads(path.read_text(encoding="utf-8-sig")) == expected


def text_equal(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    actual = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return actual == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--materialize-project-files", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))
    from src.application.storyboard_runtime.master_visual_human_approval_binding_v1 import (
        build_all,
        read_json,
        write_json,
        write_outputs,
    )

    episode = repo / "projects/episode-001-adam"
    cinematic = episode / "cinematic"
    evidence = episode / "evidence"
    contracts = episode / "contracts"

    dossier = read_json(cinematic / "master-visual-human-review-dossier-v1.json")
    critical_review = read_json(cinematic / "master-visual-critical-review-v1.json")
    prototype_plan = read_json(cinematic / "master-style-frame-prototype-plan-v1.json")
    approval_request = read_json(evidence / "master-visual-human-approval-request-v1.json")
    review_binding = read_json(contracts / "master-visual-human-review-binding-v1.json")
    definition = read_json(contracts / "episode-definition-v1.json")
    brief = read_json(cinematic / "prestige-production-brief-v2-1.json")

    (
        approval,
        receipt,
        binding,
        gate,
        updated_plan,
        updated_definition,
        updated_brief,
        markdown,
    ) = build_all(
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
        approval_request=approval_request,
        review_binding=review_binding,
        episode_definition=definition,
        production_brief=brief,
    )

    project_outputs = {
        evidence / "master-visual-human-approval-v1.json": approval,
        evidence / "master-visual-human-approval-receipt-v1.json": receipt,
        contracts / "master-visual-human-approval-binding-v1.json": binding,
        cinematic / "non-paid-master-style-frame-prototyping-gate-v1.json": gate,
        cinematic / "master-style-frame-prototype-plan-v1.json": updated_plan,
        contracts / "episode-definition-v1.json": updated_definition,
        cinematic / "prestige-production-brief-v2-1.json": updated_brief,
    }
    markdown_path = cinematic / "master-visual-human-approval-v1.md"

    if args.materialize_project_files:
        for path, payload in project_outputs.items():
            write_json(path, payload)
        markdown_path.write_text(markdown, encoding="utf-8", newline="\n")
    else:
        different = [
            str(path) for path, payload in project_outputs.items()
            if not json_equal(path, payload)
        ]
        if not text_equal(markdown_path, markdown):
            different.append(str(markdown_path))
        if different:
            raise RuntimeError(
                "Tracked master-visual human-approval files differ: "
                + ", ".join(different)
            )

    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        approval=approval,
        receipt=receipt,
        binding=binding,
        gate=gate,
        prototype_plan=updated_plan,
        episode_definition=updated_definition,
        production_brief=updated_brief,
        markdown=markdown,
    )

    print("STATUS=PASS_ADAM_MASTER_VISUAL_HUMAN_APPROVAL_BINDING_V1")
    print("CANONICAL_TIMEZONE=Asia/Baghdad")
    print("HUMAN_DECISION=APPROVE_DEVELOPMENT_BASELINE_FOR_NON_PAID_STYLE_FRAMES")
    print("DEVELOPMENT_BASELINE_APPROVAL=YES")
    print("STYLE_FRAME_IMAGE_AUTHORISATION=AUTHORIZED_NON_PAID_EIGHT_ANCHOR_PROTOTYPES_ONLY")
    print("APPROVED_PROTOTYPE_COUNT=8")
    print("MASTER_VISUAL_APPROVAL=NO")
    print("FINAL_MASTER_VISUAL_APPROVAL=NO")
    print("AUDIO_GENERATION=BLOCKED")
    print("VIDEO_GENERATION=BLOCKED")
    print("GENERATED_VIDEO_PLANNED_SECONDS=0")
    print("LIVE_EXECUTION_STATUS=BLOCKED")
    print("PAID_EXECUTION=BLOCKED")
    print("DIRECT_EXECUTION=BLOCKED")
    print("RUNWARE_EXECUTION=BLOCKED")
    print(f"APPROVAL_ID={approval['approval_id']}")
    print(f"APPROVAL_RECEIPT_ID={receipt['receipt_id']}")
    print(f"APPROVAL_BINDING_ID={binding['binding_id']}")
    print(f"STYLE_FRAME_PROTOTYPING_GATE_ID={gate['gate_id']}")
    print(f"APPROVAL_PHRASE_SHA256={approval['approval_phrase_sha256']}")
    print(f"NEXT_STAGE={updated_definition['next_stage']}")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
