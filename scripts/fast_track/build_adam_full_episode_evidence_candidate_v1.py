from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read_json_list(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list):
        raise ValueError(f"Expected JSON list: {path}")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Expected JSON object entries: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.full_episode_evidence_candidate import (
        build_approval_request,
        build_candidates,
        build_editorial_decision,
        build_integration,
        read_json,
        validate_inputs,
        write_outputs,
    )

    episode = repo / "projects/episode-001-adam"
    evidence = episode / "evidence"

    inventory = read_json(
        evidence / "full-episode-adjudication-inventory-v1.json"
    )
    event_map = read_json_list(episode / "editorial/event-map.json")
    quran = read_json(
        evidence / "quran-event-binding-candidate-v1.json"
    )
    external_scope = read_json(
        evidence / "external-event-scope-final-adjudication-v1.json"
    )
    external_pack = read_json(
        evidence / "external-event-source-candidate-pack-v1.json"
    )
    gap = read_json(evidence / "gap-human-approval-v1.json")
    origin = read_json(
        evidence / "source-origin-classification-v1.json"
    )
    delegation = read_json(
        evidence / "delegated-evidence-review-policy-v1.json"
    )
    definition = read_json(
        episode / "contracts/episode-definition-v1.json"
    )

    validate_inputs(
        inventory=inventory,
        event_map=event_map,
        quran_candidate=quran,
        external_scope=external_scope,
        external_pack=external_pack,
        gap_approval=gap,
        origin_classification=origin,
        delegation=delegation,
        episode_definition=definition,
    )
    editorial = build_editorial_decision()
    integration = build_integration(
        inventory=inventory,
        quran_candidate=quran,
        external_scope=external_scope,
        gap_approval=gap,
        editorial_decision=editorial,
    )
    (
        source_candidate,
        evidence_candidate,
        adjudication_candidate,
    ) = build_candidates(
        integration=integration,
        quran_candidate=quran,
        external_scope=external_scope,
        external_pack=external_pack,
        gap_approval=gap,
        origin_classification=origin,
        editorial_decision=editorial,
    )
    request = build_approval_request(
        integration=integration,
        source_candidate=source_candidate,
        evidence_candidate=evidence_candidate,
        adjudication_candidate=adjudication_candidate,
    )
    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        editorial_decision=editorial,
        integration=integration,
        source_candidate=source_candidate,
        evidence_candidate=evidence_candidate,
        adjudication_candidate=adjudication_candidate,
        approval_request=request,
    )

    print("STATUS=PASS_ADAM_FULL_EPISODE_EVIDENCE_CANDIDATE")
    print(f"INTEGRATION_ID={integration['integration_id']}")
    print(f"APPROVAL_REQUEST_ID={request['request_id']}")
    print("EVENT_COUNT=37")
    print("QURAN_EVENT_COUNT=19")
    print("EXTERNAL_EVENT_COUNT=14")
    print("GAP_HUMAN_EVENT_COUNT=3")
    print("EDITORIAL_EVENT_COUNT=1")
    print(f"SOURCE_COUNT={source_candidate['source_count']}")
    print(
        f"EVIDENCE_ITEM_COUNT="
        f"{evidence_candidate['evidence_item_count']}"
    )
    print("ADJUDICATION_DECISION_COUNT=37")
    print("FULL_EPISODE_EVENT_SCOPE_COMPLETE=YES")
    print("CANDIDATE_CONTRACT_VALIDATION=PASS")
    print("FINAL_HUMAN_PACKAGE_APPROVAL=NO")
    print("APPROVED_EVIDENCE_PACKAGE_COMPLETE=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(
        f"SOURCE_PACKAGE_FINGERPRINT="
        f"{source_candidate['input_fingerprint']}"
    )
    print(
        f"EVIDENCE_CANDIDATE_FINGERPRINT="
        f"{evidence_candidate['candidate_fingerprint']}"
    )
    print(
        f"ADJUDICATION_CANDIDATE_FINGERPRINT="
        f"{adjudication_candidate['candidate_fingerprint']}"
    )
    print(
        f"EXACT_APPROVAL_PHRASE_SHA256="
        f"{request['exact_approval_phrase_sha256']}"
    )
    print(
        f"EXACT_APPROVAL_PHRASE_FILE="
        f"{outputs['approval_request']}"
    )
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
