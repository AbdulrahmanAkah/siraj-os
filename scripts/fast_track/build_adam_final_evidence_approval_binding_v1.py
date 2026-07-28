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

    from src.application.storyboard_runtime.final_evidence_approval_binding import (
        APPROVED_AT_BAGHDAD,
        EXPECTED_ADJUDICATION_FINGERPRINT,
        EXPECTED_APPROVAL_PHRASE_SHA256,
        EXPECTED_EVIDENCE_FINGERPRINT,
        EXPECTED_SOURCE_FINGERPRINT,
        FINAL_ADJUDICATION_RELATIVE,
        FINAL_APPROVAL_RELATIVE,
        FINAL_BINDING_RELATIVE,
        FINAL_EVIDENCE_RELATIVE,
        FINAL_RECEIPT_RELATIVE,
        FINAL_SOURCE_RELATIVE,
        DIRECTION_RELATIVE,
        TIMEZONE,
        build_all,
        read_json,
        read_json_list,
        write_json,
        write_report,
    )

    episode = repo / "projects/episode-001-adam"
    contracts = episode / "contracts"
    evidence = episode / "evidence"
    cinematic = episode / "cinematic"

    source_candidate = read_json(
        contracts / "source-package-v1.approval-candidate.json"
    )
    evidence_candidate = read_json(
        evidence / "approved-evidence-package-v1.candidate.json"
    )
    adjudication_candidate = read_json(
        evidence / "event-evidence-adjudication-v1.candidate.json"
    )
    approval_request = read_json(
        evidence / "final-evidence-human-approval-request-v1.json"
    )
    episode_definition = read_json(
        contracts / "episode-definition-v1.json"
    )
    event_map = read_json_list(
        episode / "editorial/event-map.json"
    )
    editorial_blueprint = read_json(
        cinematic / "editorial-cinematic-blueprint-v1.json"
    )

    artifacts = build_all(
        source_candidate=source_candidate,
        evidence_candidate=evidence_candidate,
        adjudication_candidate=adjudication_candidate,
        approval_request=approval_request,
        episode_definition=episode_definition,
        event_map=event_map,
        editorial_blueprint=editorial_blueprint,
    )

    project_outputs = {
        episode / FINAL_SOURCE_RELATIVE:
            artifacts["source_package"],
        episode / FINAL_EVIDENCE_RELATIVE:
            artifacts["evidence_package"],
        episode / FINAL_ADJUDICATION_RELATIVE:
            artifacts["adjudication"],
        episode / FINAL_APPROVAL_RELATIVE:
            artifacts["approval"],
        episode / FINAL_BINDING_RELATIVE:
            artifacts["bound_blueprint"],
        episode / FINAL_RECEIPT_RELATIVE:
            artifacts["binding_receipt"],
        episode / DIRECTION_RELATIVE:
            artifacts["direction"],
        contracts / "episode-definition-v1.json":
            artifacts["episode_definition"],
    }

    if args.materialize_project_files:
        for path, payload in project_outputs.items():
            write_json(path, payload)
    else:
        missing_or_different = [
            str(path)
            for path, payload in project_outputs.items()
            if not json_equal(path, payload)
        ]
        if missing_or_different:
            raise RuntimeError(
                "Tracked final approval/binding files differ: "
                + ", ".join(missing_or_different)
            )

    outputs = write_report(
        output_root=args.output_root.resolve(),
        artifacts=artifacts,
    )
    bound = artifacts["bound_blueprint"]
    resolution = bound["event_resolution"]

    print("STATUS=PASS_ADAM_FINAL_EVIDENCE_APPROVAL_AND_STRICT_BINDING")
    print(f"APPROVED_AT_BAGHDAD={APPROVED_AT_BAGHDAD}")
    print(f"CANONICAL_TIMEZONE={TIMEZONE}")
    print("HUMAN_FINAL_EVIDENCE_APPROVAL=YES")
    print(
        f"APPROVAL_PHRASE_SHA256="
        f"{EXPECTED_APPROVAL_PHRASE_SHA256}"
    )
    print(
        f"SOURCE_CANDIDATE_FINGERPRINT="
        f"{EXPECTED_SOURCE_FINGERPRINT}"
    )
    print(
        f"EVIDENCE_CANDIDATE_FINGERPRINT="
        f"{EXPECTED_EVIDENCE_FINGERPRINT}"
    )
    print(
        f"ADJUDICATION_CANDIDATE_FINGERPRINT="
        f"{EXPECTED_ADJUDICATION_FINGERPRINT}"
    )
    print("SOURCE_COUNT=44")
    print("EVIDENCE_ITEM_COUNT=57")
    print("ADJUDICATION_DECISION_COUNT=37")
    print(
        f"INCLUDED_EVENT_COUNT="
        f"{len(resolution['included_event_ids'])}"
    )
    print(
        f"QUALIFIED_EVENT_COUNT="
        f"{len(resolution['qualified_event_ids'])}"
    )
    print(
        f"OMITTED_EVENT_COUNT="
        f"{len(resolution['omitted_event_ids'])}"
    )
    print(
        f"EDITORIAL_EVENT_COUNT="
        f"{len(resolution['editorial_event_ids'])}"
    )
    print(
        f"STORYBOARD_FRAME_COUNT="
        f"{bound['storyboard']['frame_count']}"
    )
    print(
        f"EVIDENCE_GATE_STATUS="
        f"{bound['evidence_gate_status']}"
    )
    print(
        f"LIVE_EXECUTION_STATUS="
        f"{bound['live_execution_status']}"
    )
    print(
        f"RUNWARE_EXECUTION_STATUS="
        f"{bound['runware_execution_status']}"
    )
    print("PAID_EXECUTION=BLOCKED")
    print("DIRECT_PROVIDER_EXECUTION=BLOCKED")
    print(
        "FORMAT_IDENTITY="
        "PRESTIGE_HISTORICAL_CINEMATIC_SERIES"
    )
    print(
        "DOCUMENTARY_PRESENTATION_STYLE="
        "FORBIDDEN"
    )
    print(
        "NEXT_STAGE="
        "EVIDENCE_BOUND_CINEMATIC_SCRIPT_AND_STORYBOARD_DEVELOPMENT"
    )
    print(f"BINDING_ID={bound['binding_id']}")
    print(
        f"BINDING_RECEIPT_ID="
        f"{artifacts['binding_receipt']['receipt_id']}"
    )
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
