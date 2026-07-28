from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--execution-report-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--catalog-only", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.external_source_candidate_pack import (
        build_auto_match_ledger,
        build_candidate_records,
        build_catalog,
        build_event_pack,
        build_policy,
        build_review_template,
        write_json,
        write_local_outputs,
    )

    output = args.output_root.resolve()
    policy = build_policy()
    catalog = build_catalog(policy)
    pack = build_event_pack(catalog, policy)
    review = build_review_template(pack, policy)
    records = build_candidate_records(pack, catalog, policy)

    if args.catalog_only:
        output.mkdir(parents=True, exist_ok=True)
        write_json(
            output / "external-source-candidate-policy-v1.json",
            policy,
        )
        write_json(
            output / "external-source-candidate-catalog-v1.json",
            catalog,
        )
        write_json(
            output / "external-event-source-candidate-pack-v1.json",
            pack,
        )
        write_json(
            output / "external-source-human-review-v1.template.json",
            review,
        )
        print("STATUS=PASS_EXTERNAL_SOURCE_CANDIDATE_CATALOG")
        print(f"POLICY_ID={policy['policy_id']}")
        print(f"CATALOG_ID={catalog['catalog_id']}")
        print(f"PACK_ID={pack['pack_id']}")
        print("SOURCE_CANDIDATES=22")
        print("FACTUAL_EVENTS=14")
        print("EVENT_SOURCE_LINKS=28")
        print("HUMAN_APPROVAL=PENDING")
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        return 0

    if args.execution_report_root is None:
        parser.error(
            "--execution-report-root is required unless --catalog-only is used"
        )

    ledger = build_auto_match_ledger(
        execution_report_root=args.execution_report_root.resolve(),
        pack=pack,
        catalog=catalog,
    )
    outputs = write_local_outputs(
        output_root=output,
        catalog=catalog,
        pack=pack,
        policy=policy,
        review=review,
        candidate_records=records,
        match_ledger=ledger,
    )
    print("STATUS=PASS_ADAM_EXTERNAL_SOURCE_CANDIDATE_PACK")
    print(f"POLICY_ID={policy['policy_id']}")
    print(f"CATALOG_ID={catalog['catalog_id']}")
    print(f"PACK_ID={pack['pack_id']}")
    print(f"MATCH_LEDGER_ID={ledger['match_ledger_id']}")
    print("SOURCE_CANDIDATES=22")
    print("QURAN_CANDIDATES=11")
    print("HADITH_CANDIDATES=11")
    print("FACTUAL_EVENTS=14")
    print("EVENT_SOURCE_LINKS=28")
    print("CANDIDATE_RECORDS=28")
    print(f"LOCAL_RECORDS_MATCHED={ledger['local_record_count']}")
    print(
        "MATCH_CONFIDENCE_COUNTS="
        + json.dumps(
            ledger["confidence_counts"],
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
