from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--materialization-report-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--templates-only", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.source_human_comparison_packet import (
        build_archive_integrity,
        build_comparison_packet,
        build_policy,
        build_review_template,
        load_event_pack,
        load_fetch_manifest,
        load_materialization,
        write_json,
        write_local_outputs,
    )

    output = args.output_root.resolve()
    policy = build_policy()

    if args.templates_only:
        output.mkdir(parents=True, exist_ok=True)
        blank_packet = {
            "schema_version": (
                "siraj-source-human-comparison-packet-v1"
            ),
            "status": "PENDING_LOCAL_MATERIALIZATION_REPORT",
            "comparison_packet_id": "PENDING_LOCAL_REPORT",
            "source_count": 22,
            "sources": [],
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
        blank_review = {
            "schema_version": (
                "siraj-source-human-comparison-review-template-v1"
            ),
            "status": "TEMPLATE_NOT_APPROVED",
            "episode_id": "episode-001-adam",
            "comparison_packet_id": "PENDING_LOCAL_REPORT",
            "comparison_packet_sha256": "0" * 64,
            "source_count": 22,
            "decisions": [],
            "approved_by": "",
            "approved_at": "",
            "human_comparison_complete": False,
            "source_verification_complete": False,
            "human_approval": False,
            "full_episode_adjudication_complete": False,
            "opens_evidence_gate": False,
            "evidence_gate_status": (
                "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
            ),
            "automatic_evidence_approval": "FORBIDDEN",
            "live_provider_execution": "BLOCKED",
        }
        write_json(
            output / "source-human-comparison-policy-v1.json",
            policy,
        )
        write_json(
            output / "source-human-comparison-review-v1.template.json",
            blank_review,
        )
        print("STATUS=PASS_SOURCE_HUMAN_COMPARISON_TEMPLATES")
        print(f"POLICY_ID={policy['policy_id']}")
        print("SOURCE_COUNT=22")
        print("HUMAN_APPROVAL=PENDING")
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        return 0

    if args.materialization_report_root is None:
        parser.error(
            "--materialization-report-root is required "
            "unless --templates-only is used"
        )

    report = args.materialization_report_root.resolve()
    materialization = load_materialization(
        report / "remote-source-materialization-v1.json"
    )
    fetch_manifest = load_fetch_manifest(
        report / "remote-source-fetch-manifest-v1.json"
    )
    evidence = repo / "projects/episode-001-adam/evidence"
    event_pack = load_event_pack(
        evidence / "external-event-source-candidate-pack-v1.json"
    )
    archive_integrity = build_archive_integrity(
        report_root=report,
        fetch_manifest=fetch_manifest,
    )
    packet, comparisons, events = build_comparison_packet(
        materialization=materialization,
        event_pack=event_pack,
        policy=policy,
        archive_integrity=archive_integrity,
    )
    review = build_review_template(
        packet=packet,
        comparisons=comparisons,
    )
    outputs = write_local_outputs(
        output_root=output,
        packet=packet,
        comparisons=comparisons,
        event_readiness=events,
        archive_integrity=archive_integrity,
        policy=policy,
        review=review,
    )
    print("STATUS=PASS_ADAM_SOURCE_HUMAN_COMPARISON_PACKET")
    print(
        f"COMPARISON_PACKET_ID="
        f"{packet['comparison_packet_id']}"
    )
    print(
        f"ARCHIVE_MANIFEST_ID="
        f"{archive_integrity['archive_manifest_id']}"
    )
    print(f"SOURCE_COUNT={packet['source_count']}")
    print(
        f"VALID_ARCHIVE_COUNT="
        f"{archive_integrity['valid_archive_count']}"
    )
    print(
        "COMPARISON_READINESS_COUNTS="
        + json.dumps(
            packet["comparison_readiness_counts"],
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print(f"EVENT_COUNT={events['event_count']}")
    print(
        f"EVENT_SOURCE_LINK_COUNT="
        f"{events['event_source_link_count']}"
    )
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
    print(f"ARCHIVE={outputs['zip']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
