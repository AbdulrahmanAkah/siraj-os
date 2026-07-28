from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--triage-path", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--templates-only", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.non_quran_source_verification_execution import (
        build_execution,
        build_policy,
        build_review_template,
        canonical_sha256,
        load_backlog,
        write_json,
        write_local_outputs,
    )

    backlog_path = (
        repo
        / "projects/episode-001-adam/evidence/"
        "non-quran-research-backlog-v1.json"
    )
    plan_path = (
        repo
        / "projects/episode-001-adam/evidence/"
        "non-quran-source-verification-plan-v1.json"
    )
    output = args.output_root.resolve()

    if args.templates_only:
        backlog = load_backlog(backlog_path)
        policy = build_policy()
        review = build_review_template(
            execution_id="PENDING_LOCAL_EXECUTION",
            execution_sha256="0" * 64,
            backlog=backlog,
            policy=policy,
        )
        output.mkdir(parents=True, exist_ok=True)
        write_json(
            output / "source-verification-acceptance-policy-v1.json",
            policy,
        )
        write_json(
            output / "source-verification-human-review-v1.template.json",
            review,
        )
        print("STATUS=PASS_SOURCE_VERIFICATION_TEMPLATES")
        print(f"POLICY_ID={policy['policy_id']}")
        print("HUMAN_APPROVAL=PENDING")
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        return 0

    if args.triage_path is None:
        parser.error("--triage-path is required unless --templates-only is used")

    execution, policy, review, duplicates, records = build_execution(
        triage_path=args.triage_path.resolve(),
        backlog_path=backlog_path,
        plan_path=plan_path,
    )
    outputs = write_local_outputs(
        output_root=output,
        execution=execution,
        policy=policy,
        review=review,
        duplicates=duplicates,
        record_templates=records,
    )
    print("STATUS=PASS_ADAM_SOURCE_VERIFICATION_EXECUTION")
    print(f"EXECUTION_ID={execution['execution_id']}")
    print(
        f"INPUT_SELECTED_CANDIDATES="
        f"{execution['input_selected_candidate_count']}"
    )
    print(
        f"REPRESENTATIVE_CANDIDATES="
        f"{execution['representative_candidate_count']}"
    )
    print(
        f"CONSOLIDATED_DUPLICATES="
        f"{execution['duplicate_candidate_count']}"
    )
    print(f"RECORD_TEMPLATES={execution['record_template_count']}")
    print(
        "ROUTE_COUNTS="
        + json.dumps(
            execution["route_counts"],
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print("SOURCE_VERIFICATION_COMPLETE=NO")
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
