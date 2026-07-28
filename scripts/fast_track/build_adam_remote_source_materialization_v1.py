from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--templates-only", action="store_true")
    parser.add_argument("--max-workers", type=int, default=6)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.remote_source_materialization import (
        build_event_readiness,
        build_materialization,
        build_policy,
        build_review_template,
        canonical_sha256,
        load_catalog,
        load_event_pack,
        write_json,
        write_local_outputs,
    )

    evidence = repo / "projects/episode-001-adam/evidence"
    catalog = load_catalog(
        evidence / "external-source-candidate-catalog-v1.json"
    )
    pack = load_event_pack(
        evidence / "external-event-source-candidate-pack-v1.json"
    )
    policy = build_policy()
    output = args.output_root.resolve()

    if args.templates_only:
        review = build_review_template(catalog, policy)
        output.mkdir(parents=True, exist_ok=True)
        write_json(
            output / "remote-source-materialization-policy-v1.json",
            policy,
        )
        write_json(
            output / "remote-source-human-review-v1.template.json",
            review,
        )
        print("STATUS=PASS_REMOTE_SOURCE_MATERIALIZATION_TEMPLATES")
        print(f"POLICY_ID={policy['policy_id']}")
        print("SOURCE_COUNT=22")
        print("HUMAN_APPROVAL=PENDING")
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        return 0

    materialization, manifest, raw_files, prefill = (
        build_materialization(
            catalog=catalog,
            event_pack=pack,
            policy=policy,
            max_workers=args.max_workers,
        )
    )
    review = build_review_template(
        catalog,
        policy,
        materialization_id=materialization["materialization_id"],
        materialization_sha256=canonical_sha256(materialization),
    )
    for decision in review["decisions"]:
        source = next(
            item for item in materialization["sources"]
            if item["source_candidate_id"]
            == decision["source_candidate_id"]
        )
        decision["machine_materialization_status"] = source[
            "materialization_status"
        ]
        decision["machine_extracted_text_sha256"] = source[
            "machine_extracted_text_sha256"
        ]
    readiness = build_event_readiness(materialization, pack)
    outputs = write_local_outputs(
        output_root=output,
        materialization=materialization,
        fetch_manifest=manifest,
        raw_files=raw_files,
        prefill=prefill,
        policy=policy,
        review=review,
        event_readiness=readiness,
    )
    print("STATUS=PASS_ADAM_REMOTE_SOURCE_MATERIALIZATION")
    print(
        f"MATERIALIZATION_ID="
        f"{materialization['materialization_id']}"
    )
    print(f"SOURCE_COUNT={materialization['source_count']}")
    print(
        f"FETCHED_SOURCE_COUNT="
        f"{materialization['fetched_source_count']}"
    )
    print(
        f"MACHINE_EXTRACTED_SOURCE_COUNT="
        f"{materialization['machine_extracted_source_count']}"
    )
    print(
        f"ANCHOR_MATCH_SOURCE_COUNT="
        f"{materialization['anchor_match_source_count']}"
    )
    print(
        f"ARCHIVED_RESPONSE_COUNT="
        f"{manifest['archived_response_count']}"
    )
    print(
        "MATERIALIZATION_STATUS_COUNTS="
        + json.dumps(
            materialization["status_counts"],
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print("HUMAN_SOURCE_COMPARISON=REQUIRED")
    print("SOURCE_VERIFICATION_COMPLETE=NO")
    print("AUTOMATIC_HADITH_GRADING=FORBIDDEN")
    print("AUTOMATIC_SOURCE_AUTHENTICATION=FORBIDDEN")
    print("HUMAN_APPROVAL=PENDING")
    print("FULL_EPISODE_ADJUDICATION_COMPLETE=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(f"OUTPUT_ROOT={output}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
