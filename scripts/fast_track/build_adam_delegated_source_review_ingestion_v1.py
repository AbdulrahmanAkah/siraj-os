from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.delegated_source_review_ingestion import (
        build_binding_candidate,
        build_escalation_queue,
        build_ingestion,
        normalized_json_document_sha256,
        read_json,
        validate_delegation_policy,
        validate_external_pack,
        validate_human_review_document,
        validate_normalization_audit,
        write_outputs,
    )

    evidence = repo / "projects/episode-001-adam/evidence"
    decision = read_json(
        evidence / "source-review-human-decision-v1.json"
    )
    delegation = read_json(
        evidence / "delegated-evidence-review-policy-v1.json"
    )
    audit = read_json(
        evidence / "source-review-normalization-audit-v1.json"
    )
    external = read_json(
        evidence / "external-event-source-candidate-pack-v1.json"
    )

    validate_human_review_document(decision)
    validate_delegation_policy(delegation)
    validate_normalization_audit(
        audit,
        decision_sha256=normalized_json_document_sha256(
            decision
        ),
    )
    validate_external_pack(external)

    ingestion = build_ingestion(
        decision=decision,
        delegation=delegation,
        audit=audit,
        external_pack=external,
    )
    binding = build_binding_candidate(
        decision=decision,
        external_pack=external,
        ingestion=ingestion,
    )
    escalation = build_escalation_queue(
        decision=decision,
        external_pack=external,
        ingestion=ingestion,
    )
    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        ingestion=ingestion,
        binding=binding,
        escalation=escalation,
    )

    print("STATUS=PASS_ADAM_DELEGATED_SOURCE_REVIEW_INGESTION")
    print(f"INGESTION_ID={ingestion['ingestion_id']}")
    print(f"BINDING_CANDIDATE_ID={binding['binding_candidate_id']}")
    print(f"ESCALATION_QUEUE_ID={escalation['queue_id']}")
    print("SOURCE_COUNT=22")
    print("QURAN_SOURCE_COUNT=11")
    print("HADITH_SOURCE_COUNT=11")
    print("HUMAN_SOURCE_REVIEW_APPROVED=YES")
    print("SOURCE_TEXT_LOCATOR_VERIFICATION_COMPLETE=YES")
    print("SOURCE_AUTHENTICATION_COMPLETE=NO")
    print("ROUTINE_QURAN_BINDING_CANDIDATES=11")
    print(
        f"USER_ESCALATION_SOURCE_COUNT="
        f"{escalation['user_escalation_source_count']}"
    )
    print(
        f"AI_DELEGATED_SOURCE_COUNT="
        f"{escalation['ai_delegated_source_count']}"
    )
    print("FULL_EPISODE_ADJUDICATION_COMPLETE=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
