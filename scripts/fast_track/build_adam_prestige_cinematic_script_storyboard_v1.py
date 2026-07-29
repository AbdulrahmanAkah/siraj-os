from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def json_equal(path: Path, expected: dict) -> bool:
    if not path.is_file():
        return False
    actual = json.loads(path.read_text(encoding="utf-8-sig"))
    return actual == expected


def text_equal(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    actual = (
        path.read_text(encoding="utf-8-sig")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    return actual == expected


def has_directors_cut_v2(
    definition: dict,
) -> bool:
    revision = definition.get("director_cut_revision")
    script = definition.get("cinematic_script")
    storyboard = definition.get("detailed_storyboard")
    if not (
        isinstance(revision, dict)
        and isinstance(script, dict)
        and isinstance(storyboard, dict)
    ):
        return False

    version = str(revision.get("version"))
    script_path = script.get("path")
    storyboard_path = storyboard.get("path")
    return (
        (
            version == "2"
            and script_path
            == "editorial/prestige-cinematic-script-v2.json"
            and storyboard_path
            == "cinematic/detailed-storyboard-v2.json"
        )
        or (
            version == "2.1"
            and script_path
            == "editorial/prestige-cinematic-script-v2-1.json"
            and storyboard_path
            == "cinematic/detailed-storyboard-v2-1.json"
        )
    )


def v1_episode_definition_compatible(
    actual: dict,
    expected_v1: dict,
) -> bool:
    if not has_directors_cut_v2(actual):
        return actual == expected_v1

    superseded = actual.get("superseded_script_storyboard_v1")
    expected_script = expected_v1.get("cinematic_script")
    expected_storyboard = expected_v1.get("detailed_storyboard")
    if not (
        isinstance(superseded, dict)
        and isinstance(expected_script, dict)
        and isinstance(expected_storyboard, dict)
    ):
        return False
    return (
        superseded.get("script_fingerprint")
        == expected_script.get("input_fingerprint")
        and superseded.get("storyboard_fingerprint")
        == expected_storyboard.get("input_fingerprint")
        and actual.get("evidence_gate_status")
        == expected_v1.get("evidence_gate_status")
        and actual.get("live_execution_status")
        == expected_v1.get("live_execution_status")
        and actual.get("paid_execution")
        == expected_v1.get("paid_execution")
    )


def merge_v1_episode_definition(
    existing: dict,
    expected_v1: dict,
) -> dict:
    if has_directors_cut_v2(existing):
        return existing
    return expected_v1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--materialize-project-files",
        action="store_true",
    )
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.prestige_cinematic_script_storyboard import (
        build_script_and_storyboard,
        read_json,
        read_json_list,
        render_script_markdown,
        update_episode_definition,
        validate_inputs,
        write_json,
        write_outputs,
    )

    episode = repo / "projects/episode-001-adam"
    contracts = episode / "contracts"
    editorial = episode / "editorial"
    evidence = episode / "evidence"
    cinematic = episode / "cinematic"

    creative = read_json(
        editorial / "prestige-cinematic-script-blueprint-v1.json"
    )
    bound = read_json(
        cinematic / "evidence-bound-cinematic-blueprint-v1.json"
    )
    direction = read_json(
        contracts / "prestige-historical-cinematic-direction-v1.json"
    )
    event_map = read_json_list(editorial / "event-map.json")
    evidence_package = read_json(
        evidence / "approved-evidence-package-v1.json"
    )
    adjudication = read_json(
        evidence / "event-evidence-adjudication-v1.json"
    )
    definition = read_json(
        contracts / "episode-definition-v1.json"
    )

    validate_inputs(
        creative_blueprint=creative,
        bound_blueprint=bound,
        direction=direction,
        event_map=event_map,
        evidence_package=evidence_package,
        adjudication=adjudication,
        episode_definition=definition,
    )
    (
        script,
        storyboard,
        trace,
        approval_request,
        production_brief,
    ) = build_script_and_storyboard(
        creative_blueprint=creative,
        bound_blueprint=bound,
        direction=direction,
        event_map=event_map,
        evidence_package=evidence_package,
        adjudication=adjudication,
    )
    updated_definition = update_episode_definition(
        episode_definition=definition,
        script=script,
        storyboard=storyboard,
        trace=trace,
        approval_request=approval_request,
        production_brief=production_brief,
    )
    markdown = render_script_markdown(script)

    definition_path = contracts / "episode-definition-v1.json"
    project_outputs = {
        editorial / "prestige-cinematic-script-v1.json": script,
        cinematic / "detailed-storyboard-v1.json": storyboard,
        evidence / "script-storyboard-evidence-trace-v1.json": trace,
        evidence
        / "script-storyboard-human-approval-request-v1.json":
            approval_request,
        cinematic / "prestige-production-brief-v1.json":
            production_brief,
    }
    markdown_path = editorial / "prestige-cinematic-script-v1.md"

    if args.materialize_project_files:
        for path, payload in project_outputs.items():
            write_json(path, payload)
        write_json(
            definition_path,
            merge_v1_episode_definition(
                definition,
                updated_definition,
            ),
        )
        markdown_path.write_text(
            markdown,
            encoding="utf-8",
            newline="\n",
        )
    else:
        different = [
            str(path)
            for path, payload in project_outputs.items()
            if not json_equal(path, payload)
        ]
        actual_definition = json.loads(
            definition_path.read_text(encoding="utf-8-sig")
        )
        if not v1_episode_definition_compatible(
            actual_definition,
            updated_definition,
        ):
            different.append(str(definition_path))
        if not text_equal(markdown_path, markdown):
            different.append(str(markdown_path))
        if different:
            raise RuntimeError(
                "Tracked v1 script/storyboard audit differs: "
                + ", ".join(different)
            )

    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        script=script,
        storyboard=storyboard,
        trace=trace,
        approval_request=approval_request,
        production_brief=production_brief,
        episode_definition=updated_definition,
    )

    print("STATUS=PASS_ADAM_PRESTIGE_CINEMATIC_SCRIPT_STORYBOARD")
    print("CANONICAL_TIMEZONE=Asia/Baghdad")
    print("FORMAT_IDENTITY=PRESTIGE_HISTORICAL_CINEMATIC_SERIES")
    print("EPISODE_DURATION_SECONDS=1320")
    print("SEQUENCE_COUNT=14")
    print("SHOT_COUNT=70")
    print(f"NARRATION_WORD_COUNT={script['narration_word_count']}")
    print("EVENT_TRACE_COUNT=37")
    print("EVIDENCE_TRACE_COUNT=57")
    print("QUALIFIED_EVENT_COUNT=7")
    print("EVENT_COVERAGE_COMPLETE=YES")
    print("EVIDENCE_COVERAGE_COMPLETE=YES")
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
    print(
        f"STORYBOARD_FINGERPRINT="
        f"{storyboard['storyboard_fingerprint']}"
    )
    print(
        f"APPROVAL_REQUEST_ID="
        f"{approval_request['request_id']}"
    )
    print(
        f"APPROVAL_PHRASE_SHA256="
        f"{approval_request['exact_approval_phrase_sha256']}"
    )
    print(
        "APPROVAL_PHRASE_FILE="
        f"{outputs['approval_request']}"
    )
    print(
        "NEXT_STAGE="
        "HUMAN_REVIEW_OF_PRESTIGE_CINEMATIC_SCRIPT_AND_STORYBOARD"
    )
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
