from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--review-report-root", type=Path)
    parser.add_argument("--materialization-report-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--templates-only", action="store_true")
    parser.add_argument("--validate-decisions", type=Path)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.source_review_workbench import (
        build_decision_template,
        build_json_schema,
        build_manifest,
        build_policy,
        canonical_sha256,
        load_docket,
        load_events,
        load_materialization,
        load_resolution,
        render_workbench_html,
        validate_human_decision,
        write_json,
        write_local_outputs,
    )

    output = args.output_root.resolve()
    policy = build_policy()

    if args.templates_only:
        output.mkdir(parents=True, exist_ok=True)
        generic = {
            "schema_version": (
                "siraj-source-review-human-decision-template-v1"
            ),
            "status": "EDITABLE_DRAFT_NOT_APPROVED",
            "episode_id": "episode-001-adam",
            "docket_id": "PENDING_LOCAL_REPORT",
            "docket_sha256": "0" * 64,
            "policy_id": policy["policy_id"],
            "policy_sha256": canonical_sha256(policy),
            "source_count": 22,
            "decisions": [],
            "approved_by": "",
            "approved_at": "",
            "approval_phrase": "",
            "human_comparison_complete": False,
            "source_verification_complete": False,
            "human_approval": False,
            "full_episode_adjudication_complete": False,
            "approved_evidence_package_complete": False,
            "opens_evidence_gate": False,
            "evidence_gate_status": (
                "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
            ),
            "automatic_evidence_approval": "FORBIDDEN",
            "live_provider_execution": "BLOCKED",
        }
        write_json(
            output / "source-review-workbench-policy-v1.json",
            policy,
        )
        write_json(
            output
            / "source-review-human-decision-v1.template.json",
            generic,
        )
        write_json(
            output
            / "source-review-human-decision-json-schema-v1.json",
            build_json_schema(),
        )
        print("STATUS=PASS_SOURCE_REVIEW_WORKBENCH_TEMPLATES")
        print(f"POLICY_ID={policy['policy_id']}")
        print("SOURCE_COUNT=22")
        print("HUMAN_DECISIONS_RECORDED=0")
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        return 0

    if (
        args.review_report_root is None
        or args.materialization_report_root is None
    ):
        parser.error(
            "--review-report-root and "
            "--materialization-report-root are required"
        )

    review = args.review_report_root.resolve()
    materialization_root = (
        args.materialization_report_root.resolve()
    )
    docket = load_docket(
        review / "source-review-docket-v1.json"
    )
    resolution = load_resolution(
        review / "partial-source-resolution-v1.json"
    )
    events = load_events(
        review / "event-source-review-readiness-v1.json"
    )
    materialization = load_materialization(
        materialization_root
        / "remote-source-materialization-v1.json"
    )

    if args.validate_decisions:
        data = json.loads(
            args.validate_decisions.resolve().read_text(
                encoding="utf-8-sig"
            )
        )
        report = validate_human_decision(
            data,
            docket=docket,
            policy=policy,
            require_final=args.final,
        )
        output.mkdir(parents=True, exist_ok=True)
        report_path = (
            output / "source-review-validation-report-v1.json"
        )
        write_json(report_path, report)
        print(f"STATUS={report['status']}")
        print(
            f"VALID_SOURCE_DECISIONS="
            f"{report['valid_source_decision_count']}"
        )
        print(
            f"INVALID_SOURCE_DECISIONS="
            f"{report['invalid_source_decision_count']}"
        )
        print(
            f"HUMAN_COMPARISON_COMPLETE="
            f"{'YES' if report['computed_human_comparison_complete'] else 'NO'}"
        )
        print(
            f"SOURCE_VERIFICATION_COMPLETE="
            f"{'YES' if report['computed_source_verification_complete'] else 'NO'}"
        )
        print(
            f"HUMAN_APPROVAL="
            f"{'YES' if report['human_approval'] else 'NO'}"
        )
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        print(f"REPORT={report_path}")
        return 0 if not report["errors"] else 1

    manifest = build_manifest(
        docket=docket,
        resolution=resolution,
        events=events,
        materialization=materialization,
        policy=policy,
    )
    template = build_decision_template(
        docket=docket, policy=policy
    )
    html = render_workbench_html(
        manifest=manifest,
        template=template,
        policy=policy,
    )
    outputs = write_local_outputs(
        output_root=output,
        manifest=manifest,
        template=template,
        policy=policy,
        json_schema=build_json_schema(),
        html_text=html,
    )
    print("STATUS=PASS_ADAM_SOURCE_REVIEW_WORKBENCH")
    print(
        f"WORKBENCH_MANIFEST_ID="
        f"{manifest['workbench_manifest_id']}"
    )
    print(f"DOCKET_ID={manifest['docket_id']}")
    print(f"SOURCE_COUNT={manifest['source_count']}")
    print(f"EVENT_COUNT={manifest['event_count']}")
    print(
        f"EVENT_SOURCE_LINK_COUNT="
        f"{manifest['event_source_link_count']}"
    )
    print("ORIGINAL_READY_SOURCES=17")
    print("REFINED_READY_SOURCES=5")
    print("REMAINING_RESOLUTION_SOURCES=0")
    print("HUMAN_DECISIONS_RECORDED=0")
    print("HUMAN_COMPARISON_COMPLETE=NO")
    print("SOURCE_VERIFICATION_COMPLETE=NO")
    print("HUMAN_APPROVAL=PENDING")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(f"WORKBENCH_HTML={outputs['html']}")
    print(f"OUTPUT_ROOT={output}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
