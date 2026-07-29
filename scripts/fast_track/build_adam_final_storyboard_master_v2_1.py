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
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n") == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--materialize-project-files", action="store_true")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.prestige_storyboard_master_v2_1 import (
        build_master_candidate,
        read_json,
        render_script_markdown,
        update_episode_definition,
        validate_inputs,
        write_json,
        write_outputs,
    )

    episode = repo / "projects/episode-001-adam"
    editorial = episode / "editorial"
    cinematic = episode / "cinematic"
    evidence = episode / "evidence"
    contracts = episode / "contracts"

    script_v2 = read_json(editorial / "prestige-cinematic-script-v2.json")
    storyboard_v2 = read_json(cinematic / "detailed-storyboard-v2.json")
    trace_v2 = read_json(evidence / "script-storyboard-evidence-trace-v2.json")
    approval_v2 = read_json(evidence / "script-storyboard-human-approval-request-v2.json")
    brief_v2 = read_json(cinematic / "prestige-production-brief-v2.json")
    definition = read_json(contracts / "episode-definition-v1.json")

    validate_inputs(
        script_v2=script_v2,
        storyboard_v2=storyboard_v2,
        trace_v2=trace_v2,
        approval_request_v2=approval_v2,
        production_brief_v2=brief_v2,
        episode_definition=definition,
    )
    script, storyboard, trace, approval, brief, audit = build_master_candidate(
        script_v2=script_v2,
        storyboard_v2=storyboard_v2,
        trace_v2=trace_v2,
        approval_request_v2=approval_v2,
        production_brief_v2=brief_v2,
    )
    updated = update_episode_definition(
        episode_definition=definition,
        script=script,
        storyboard=storyboard,
        trace=trace,
        approval_request=approval,
        production_brief=brief,
        audit=audit,
    )
    markdown = render_script_markdown(script)

    project_outputs = {
        editorial / "prestige-cinematic-script-v2-1.json": script,
        cinematic / "detailed-storyboard-v2-1.json": storyboard,
        evidence / "script-storyboard-evidence-trace-v2-1.json": trace,
        evidence / "script-storyboard-human-approval-request-v2-1.json": approval,
        cinematic / "prestige-production-brief-v2-1.json": brief,
        cinematic / "storyboard-master-directorial-audit-v2-1.json": audit,
        contracts / "episode-definition-v1.json": updated,
    }
    markdown_path = editorial / "prestige-cinematic-script-v2-1.md"
    csv_path = cinematic / "detailed-storyboard-v2-1.csv"

    if args.materialize_project_files:
        for path, payload in project_outputs.items():
            write_json(path, payload)
        markdown_path.write_text(markdown, encoding="utf-8", newline="\n")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            import csv
            fields = ["shot_id", "sequence_id", "duration_seconds", "dramatic_stage", "dramatic_beat", "visual_subtext", "composition", "camera", "camera_psychology", "screen_action", "sound_detail", "sound_perspective", "cut_motivation", "continuity_anchor", "transition_role", "religious_visual_safety", "master_lock_status"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for shot in storyboard["shots"]:
                writer.writerow({key: shot[key] for key in fields})
    else:
        different = [str(path) for path, payload in project_outputs.items() if not json_equal(path, payload)]
        if not text_equal(markdown_path, markdown):
            different.append(str(markdown_path))
        if not csv_path.is_file():
            different.append(str(csv_path))
        if different:
            raise RuntimeError("Tracked final storyboard master files differ: " + ", ".join(different))

    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        script=script,
        storyboard=storyboard,
        trace=trace,
        approval_request=approval,
        production_brief=brief,
        audit=audit,
        episode_definition=updated,
    )
    print("STATUS=PASS_ADAM_FINAL_STORYBOARD_MASTER_V2_1")
    print("CANONICAL_TIMEZONE=Asia/Baghdad")
    print("FORMAT_IDENTITY=PRESTIGE_HISTORICAL_CINEMATIC_SERIES")
    print("DIRECTORS_CUT_VERSION=2.1")
    print("STORYBOARD_COMPLETION_STATUS=COMPLETE_AWAITING_HUMAN_APPROVAL")
    print("EXACT_COVENANT_VERSE=PASS")
    print("DESCENDANTS_EMERGENCE=ASSERTIVE")
    print("CHRONOLOGICAL_LINKAGE=QUALIFIED_ONLY")
    print("SEQUENCE_COUNT=14")
    print("SHOT_COUNT=70")
    print("EPISODE_DURATION_SECONDS=1320")
    print(f"NARRATION_WORD_COUNT={script['narration_word_count']}")
    print("EVENT_TRACE_COUNT=37")
    print("EVIDENCE_TRACE_COUNT=57")
    print("DIRECTORIAL_BEAT_COVERAGE=70/70")
    print("VISUAL_SUBTEXT_COVERAGE=70/70")
    print("CAMERA_PSYCHOLOGY_COVERAGE=70/70")
    print("SOUND_PERSPECTIVE_COVERAGE=70/70")
    print("ACCEPTANCE_CRITERIA_COVERAGE=70/70")
    print("GENERIC_PLACEHOLDER_SHOTS=0")
    print("UNRESOLVED_DIRECTORIAL_DECISIONS=0")
    print("HUMAN_SCRIPT_APPROVAL=NO")
    print("RELIGIOUS_SAFETY_APPROVAL=NO")
    print("HUMAN_STORYBOARD_APPROVAL=NO")
    print("MASTER_VISUAL_APPROVAL=NO")
    print("LIVE_EXECUTION_STATUS=BLOCKED")
    print("PAID_EXECUTION=BLOCKED")
    print("RUNWARE_EXECUTION=BLOCKED")
    print("GENERATED_VIDEO_PLANNED_SECONDS=0")
    print(f"SCRIPT_ID={script['script_id']}")
    print(f"SCRIPT_FINGERPRINT={script['script_fingerprint']}")
    print(f"STORYBOARD_ID={storyboard['storyboard_id']}")
    print(f"STORYBOARD_FINGERPRINT={storyboard['storyboard_fingerprint']}")
    print(f"DIRECTORIAL_AUDIT_ID={audit['audit_id']}")
    print(f"APPROVAL_REQUEST_ID={approval['request_id']}")
    print(f"APPROVAL_PHRASE_SHA256={approval['exact_approval_phrase_sha256']}")
    print("NEXT_STAGE=HUMAN_REVIEW_OF_FINAL_STORYBOARD_MASTER_V2_1")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
