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

    from src.application.storyboard_runtime.high_importance_evidence_resolution import (
        build_final_external_scope,
        build_human_approval,
        build_progress,
        read_json,
        validate_inputs,
        write_outputs,
    )

    evidence = repo / "projects/episode-001-adam/evidence"
    dossier = read_json(
        evidence / "high-importance-evidence-review-dossier-v1.json"
    )
    event_scope = read_json(
        evidence / "routine-event-scope-adjudication-v1.json"
    )
    research = read_json(
        evidence / "delegated-hadith-authentication-research-v1.json"
    )
    prior_gap = read_json(evidence / "gap-human-approval-v1.json")
    origin = read_json(
        evidence / "source-origin-classification-v1.json"
    )

    validate_inputs(
        dossier=dossier,
        event_scope=event_scope,
        research=research,
        prior_gap_approval=prior_gap,
        origin_classification=origin,
    )
    approval = build_human_approval(
        dossier=dossier,
        prior_gap_approval=prior_gap,
        origin_classification=origin,
    )
    final_scope = build_final_external_scope(
        event_scope=event_scope,
        approval=approval,
    )
    progress = build_progress(
        approval=approval,
        final_scope=final_scope,
    )
    outputs = write_outputs(
        output_root=args.output_root.resolve(),
        approval=approval,
        final_scope=final_scope,
        progress=progress,
    )

    print("STATUS=PASS_ADAM_HIGH_IMPORTANCE_EVIDENCE_RESOLUTION")
    print(f"APPROVAL_ID={approval['approval_id']}")
    print(f"FINAL_SCOPE_ID={final_scope['adjudication_id']}")
    print(f"PROGRESS_ID={progress['progress_id']}")
    print("HIGH_IMPORTANCE_SOURCE_DECISIONS=3")
    print("HIGH_IMPORTANCE_EVENT_DECISIONS=6")
    print("PEN_FIRSTNESS=ASSERTIVE_BY_EXPLICIT_HADITH_TEXT")
    print("IBLIS_PRIOR_EXISTENCE=QUALIFIED_NOT_CERTAIN")
    print("CLAY_DESCRIPTIONS=ASSERTIVE_CHRONOLOGY_QUALIFIED")
    print("TAFSIR_SUPPLEMENTS=ALLOWED_WITH_ATTRIBUTION")
    print("ISRAILIYYAT=EXPLICIT_LABEL_AND_NO_CERTAINTY")
    print("HAWWA_NAME=AUTHENTIC_SUNNAH")
    print("HAWWA_CREATED_FROM_ADAM_RIB=SUPPORTED_SYNTHESIS_APPROVED")
    print("EXTERNAL_EVENT_SCOPE_COMPLETE=YES")
    print("EXTERNAL_EVENT_COUNT=14")
    print("FULL_EPISODE_ADJUDICATION_COMPLETE=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(f"OUTPUT_ROOT={args.output_root.resolve()}")
    print(f"ARCHIVE={outputs['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
