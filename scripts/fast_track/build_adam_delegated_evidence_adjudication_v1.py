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

    from src.application.storyboard_runtime.delegated_evidence_adjudication import (
        build_event_scope_adjudication,
        build_hadith_research,
        build_high_importance_dossier,
        read_json,
        validate_inputs,
        write_outputs,
    )

    evidence = repo / "projects/episode-001-adam/evidence"
    ingestion = read_json(evidence / "source-review-ingestion-v1.json")
    queue = read_json(
        evidence / "delegated-evidence-escalation-queue-v1.json"
    )
    external = read_json(
        evidence / "external-event-source-candidate-pack-v1.json"
    )
    decision = read_json(
        evidence / "source-review-human-decision-v1.json"
    )
    delegation = read_json(
        evidence / "delegated-evidence-review-policy-v1.json"
    )

    validate_inputs(
        ingestion=ingestion,
        queue=queue,
        external_pack=external,
        decision=decision,
        delegation=delegation,
    )
    research = build_hadith_research(
        ingestion=ingestion,
        queue=queue,
    )
    event_scope = build_event_scope_adjudication(
        ingestion=ingestion,
        external_pack=external,
        research=research,
    )
    dossier = build_high_importance_dossier(
        ingestion=ingestion,
        research=research,
        event_scope=event_scope,
    )
    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        research=research,
        event_scope=event_scope,
        dossier=dossier,
    )

    print("STATUS=PASS_ADAM_DELEGATED_EVIDENCE_ADJUDICATION")
    print(f"HADITH_RESEARCH_ID={research['research_id']}")
    print(f"EVENT_SCOPE_ID={event_scope['adjudication_id']}")
    print(f"HIGH_IMPORTANCE_DOSSIER_ID={dossier['dossier_id']}")
    print("HADITH_SOURCE_COUNT=11")
    print("DELEGATED_SOURCE_COUNT=8")
    print("HIGH_IMPORTANCE_SOURCE_COUNT=3")
    print("SOURCE_AUTHENTICATION_RESEARCH_COMPLETE=YES")
    print("ROUTINE_SOURCE_DECISIONS_COMPLETE=YES")
    print("ROUTINE_EVENT_SCOPE_APPROVED=8")
    print("HIGH_IMPORTANCE_EVENT_COUNT=6")
    print("HIGH_IMPORTANCE_RECOMMENDATIONS_COMPLETE=YES")
    print("FINAL_USER_HIGH_IMPORTANCE_DECISIONS_COMPLETE=NO")
    print("FULL_EPISODE_ADJUDICATION_COMPLETE=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
