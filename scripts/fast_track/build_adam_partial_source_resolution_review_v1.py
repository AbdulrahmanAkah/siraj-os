from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--materialization-report-root", type=Path)
    parser.add_argument("--comparison-report-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--templates-only", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.partial_source_resolution_review import (
        build_decision_template,
        build_human_approval_text,
        build_policy,
        build_resolution_and_docket,
        load_comparison_packet,
        load_comparisons,
        load_event_pack,
        load_materialization,
        write_json,
        write_local_outputs,
    )

    output = args.output_root.resolve()
    policy = build_policy()

    if args.templates_only:
        output.mkdir(parents=True, exist_ok=True)
        blank = {
            "schema_version": (
                "siraj-source-review-decision-template-v1"
            ),
            "status": "TEMPLATE_NOT_APPROVED",
            "episode_id": "episode-001-adam",
            "docket_id": "PENDING_LOCAL_REPORT",
            "docket_sha256": "0" * 64,
            "policy_id": policy["policy_id"],
            "policy_sha256": __import__("hashlib").sha256(
                json.dumps(
                    policy,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "source_count": 22,
            "decisions": [],
            "approved_by": "",
            "approved_at": "",
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
            output / "source-review-policy-v1.json",
            policy,
        )
        write_json(
            output / "source-review-decision-v1.template.json",
            blank,
        )
        print("STATUS=PASS_SOURCE_REVIEW_TEMPLATES")
        print(f"POLICY_ID={policy['policy_id']}")
        print("SOURCE_COUNT=22")
        print("HUMAN_APPROVAL=PENDING")
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        return 0

    if (
        args.materialization_report_root is None
        or args.comparison_report_root is None
    ):
        parser.error(
            "--materialization-report-root and "
            "--comparison-report-root are required"
        )

    materialization_root = (
        args.materialization_report_root.resolve()
    )
    comparison_root = args.comparison_report_root.resolve()
    materialization = load_materialization(
        materialization_root
        / "remote-source-materialization-v1.json"
    )
    packet = load_comparison_packet(
        comparison_root
        / "source-human-comparison-packet-v1.json"
    )
    comparisons = load_comparisons(
        comparison_root, packet
    )
    event_pack = load_event_pack(
        repo
        / "projects/episode-001-adam/evidence/"
        "external-event-source-candidate-pack-v1.json"
    )
    resolution, docket, events, notebook = (
        build_resolution_and_docket(
            materialization=materialization,
            comparison_packet=packet,
            comparisons=comparisons,
            event_pack=event_pack,
            policy=policy,
        )
    )
    decision = build_decision_template(
        docket=docket,
        policy=policy,
    )
    approval_text = build_human_approval_text(
        docket=docket,
        decision_template=decision,
    )
    outputs = write_local_outputs(
        output_root=output,
        resolution=resolution,
        docket=docket,
        events=events,
        notebook=notebook,
        policy=policy,
        decision_template=decision,
        approval_text=approval_text,
    )
    print(
        "STATUS=PASS_ADAM_PARTIAL_SOURCE_RESOLUTION_AND_REVIEW_DOCKET"
    )
    print(f"RESOLUTION_ID={resolution['resolution_id']}")
    print(f"DOCKET_ID={docket['docket_id']}")
    print(f"SOURCE_COUNT={docket['source_count']}")
    print(
        f"ORIGINAL_PARTIAL_SOURCE_COUNT="
        f"{resolution['original_partial_source_count']}"
    )
    print(
        f"NEWLY_READY_SOURCE_COUNT="
        f"{resolution['newly_ready_source_count']}"
    )
    print(
        f"REMAINING_RESOLUTION_SOURCE_COUNT="
        f"{resolution['remaining_resolution_source_count']}"
    )
    print(
        "REMAINING_RESOLUTION_SOURCE_IDS="
        + json.dumps(
            resolution["remaining_resolution_source_ids"],
            ensure_ascii=False,
        )
    )
    print(
        "REFINED_READINESS_COUNTS="
        + json.dumps(
            resolution["refined_readiness_counts"],
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print(
        f"NOTEBOOKLM_TARGET_SOURCE_COUNT="
        f"{notebook['target_source_count']}"
    )
    print(f"EVENT_COUNT={events['event_count']}")
    print(
        f"EVENT_SOURCE_LINK_COUNT="
        f"{events['event_source_link_count']}"
    )
    print("HUMAN_DECISIONS_RECORDED=0")
    print("HUMAN_COMPARISON_COMPLETE=NO")
    print("SOURCE_VERIFICATION_COMPLETE=NO")
    print("AUTOMATIC_HADITH_GRADING=FORBIDDEN")
    print("AUTOMATIC_SOURCE_AUTHENTICATION=FORBIDDEN")
    print("AUTOMATIC_ORIGIN_CLASSIFICATION=FORBIDDEN")
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
