from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--harvest-path", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--policy-only", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.non_quran_candidate_triage import (
        build_policy,
        build_review_template,
        build_triage,
        build_verification_plan,
        load_backlog,
        write_json,
        write_local_outputs,
    )

    backlog_path = (
        repo
        / "projects/episode-001-adam/evidence/"
        "non-quran-research-backlog-v1.json"
    )
    backlog = load_backlog(backlog_path)
    policy = build_policy()
    review = build_review_template(backlog, policy)
    plan = build_verification_plan(backlog, policy)
    output = args.output_root.resolve()

    if args.policy_only:
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "non-quran-candidate-triage-policy-v1.json", policy)
        write_json(
            output / "non-quran-candidate-human-review-v1.template.json",
            review,
        )
        write_json(
            output / "non-quran-source-verification-plan-v1.json",
            plan,
        )
        print("STATUS=PASS_NON_QURAN_CANDIDATE_TRIAGE_POLICY")
        print(f"POLICY_ID={policy['policy_id']}")
        print("FACTUAL_EVENTS=14")
        print("EDITORIAL_EVENTS=1")
        print("HUMAN_APPROVAL=PENDING")
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        return 0

    if args.harvest_path is None:
        parser.error("--harvest-path is required unless --policy-only is used")

    triage, policy, review, plan, clusters, locators = build_triage(
        harvest_path=args.harvest_path.resolve(),
        backlog_path=backlog_path,
    )
    outputs = write_local_outputs(
        output_root=output,
        triage=triage,
        policy=policy,
        review=review,
        plan=plan,
        clusters=clusters,
        locator_index=locators,
    )
    print("STATUS=PASS_ADAM_NON_QURAN_CANDIDATE_TRIAGE")
    print(f"TRIAGE_ID={triage['triage_id']}")
    print(f"INPUT_CANDIDATES={triage['input_candidate_count']}")
    print(f"SELECTED_CANDIDATES={triage['selected_candidate_count']}")
    print(
        f"EVENTS_WITH_LOCATOR_CANDIDATES="
        f"{triage['events_with_locator_candidates']}"
    )
    print(
        f"MANUAL_DISCOVERY_EVENTS="
        f"{len(triage['events_requiring_manual_source_discovery'])}"
    )
    print(f"STRUCTURAL_CLUSTERS={triage['cluster_count']}")
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
