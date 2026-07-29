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

    from src.application.storyboard_runtime.master_visual_human_review_v1 import (
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
    visual_bible = read_json(cinematic / "master-visual-bible-v1.json")
    color_script = read_json(cinematic / "color-script-v1.json")
    animatic = read_json(cinematic / "non-paid-animatic-development-v1.json")
    development_audit = read_json(
        cinematic / "master-visual-development-audit-v1.json"
    )
    development_binding = read_json(
        contracts / "master-visual-development-binding-v1.json"
    )
    definition = read_json(contracts / "episode-definition-v1.json")
    brief = read_json(cinematic / "prestige-production-brief-v2-1.json")

    (
        dossier,
        critical_review,
        prototype_plan,
        approval_request,
        review_binding,
        updated_definition,
        updated_brief,
        markdown,
    ) = build_all(
        storyboard=storyboard,
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
        development_audit=development_audit,
        development_binding=development_binding,
        episode_definition=definition,
        production_brief=brief,
    )

    project_outputs = {
        cinematic / "master-visual-human-review-dossier-v1.json": dossier,
        cinematic / "master-visual-critical-review-v1.json": critical_review,
        cinematic / "master-style-frame-prototype-plan-v1.json": prototype_plan,
        evidence / "master-visual-human-approval-request-v1.json": approval_request,
        contracts / "master-visual-human-review-binding-v1.json": review_binding,
        contracts / "episode-definition-v1.json": updated_definition,
        cinematic / "prestige-production-brief-v2-1.json": updated_brief,
    }
    markdown_path = cinematic / "master-visual-human-review-v1.md"

    if args.materialize_project_files:
        for path, payload in project_outputs.items():
            write_json(path, payload)
        markdown_path.write_text(markdown, encoding="utf-8", newline="\n")
    else:
        different = [
            str(path)
            for path, payload in project_outputs.items()
            if not json_equal(path, payload)
        ]
        if not text_equal(markdown_path, markdown):
            different.append(str(markdown_path))
        if different:
            raise RuntimeError(
                "Tracked master-visual human-review files differ: "
                + ", ".join(different)
            )

    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
        approval_request=approval_request,
        review_binding=review_binding,
        episode_definition=updated_definition,
        production_brief=updated_brief,
        markdown=markdown,
    )

    print("STATUS=PASS_ADAM_MASTER_VISUAL_HUMAN_REVIEW_V1")
    print("CANONICAL_TIMEZONE=Asia/Baghdad")
    print("REVIEW_DOSSIER_STATUS=READY_FOR_HUMAN_DECISION_ON_DEVELOPMENT_BASELINE")
    print("CRITICAL_REVIEW_STATUS=PASS_REVIEW_READY_WITH_FINAL_APPROVAL_BLOCKERS")
    print("DEVELOPMENT_BASELINE_BLOCKERS=0")
    print("FINAL_MASTER_VISUAL_APPROVAL_BLOCKERS=3")
    print("STYLE_FRAME_PROTOTYPE_PLAN=8_ANCHOR_FRAMES_PLANNED")
    print("STYLE_FRAME_IMAGE_AUTHORISATION=PENDING_HUMAN_APPROVAL")
    print("HUMAN_DECISION=PENDING")
    print("MASTER_VISUAL_APPROVAL=NO")
    print("FINAL_MASTER_VISUAL_APPROVAL_ELIGIBLE=NO")
    print("MEDIA_ASSETS_CREATED=0")
    print("GENERATED_VIDEO_PLANNED_SECONDS=0")
    print("LIVE_EXECUTION_STATUS=BLOCKED")
    print("PAID_EXECUTION=BLOCKED")
    print("DIRECT_EXECUTION=BLOCKED")
    print("RUNWARE_EXECUTION=BLOCKED")
    print(f"REVIEW_DOSSIER_ID={dossier['review_dossier_id']}")
    print(f"CRITICAL_REVIEW_ID={critical_review['critical_review_id']}")
    print(f"PROTOTYPE_PLAN_ID={prototype_plan['prototype_plan_id']}")
    print(f"APPROVAL_REQUEST_ID={approval_request['request_id']}")
    print(f"REVIEW_BINDING_ID={review_binding['review_binding_id']}")
    print(f"APPROVAL_PHRASE_SHA256={approval_request['exact_approval_phrase_sha256']}")
    print(f"EXACT_APPROVAL_PHRASE={approval_request['exact_approval_phrase']}")
    print(f"NEXT_STAGE={updated_definition['next_stage']}")
    print(f"APPROVED_NEXT_STAGE={approval_request['approval_effect_next_stage']}")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
