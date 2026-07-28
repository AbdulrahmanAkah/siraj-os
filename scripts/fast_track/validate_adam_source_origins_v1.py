from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _bootstrap(repo_root: Path) -> None:
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Adam source-origin classification and proposal."
    )
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    _bootstrap(repo_root)

    from application.storyboard_runtime.source_origin_classification import (
        load_and_validate_bundle,
        write_validation_manifest,
    )

    bundle = load_and_validate_bundle(repo_root)
    manifest = write_validation_manifest(repo_root, Path(args.output))
    classification = bundle["classification"]
    proposal = bundle["proposal"]

    print("STATUS=PASS_ADAM_SOURCE_ORIGIN_CLASSIFICATION")
    print(f"CLASSIFICATION_ID={classification['classification_id']}")
    print("TARGET_EVENTS=3")
    print("LONELINESS_ORIGIN=TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU")
    print("LONELINESS_ASSERTIVE_NARRATION=NO")
    print("LEFT_RIB_SLEEP_ORIGIN=ISRAILIYYAT_EXPLICIT_ORIGIN")
    print("SUPPORTED_SYNTHESIS=HAWA_CREATED_FROM_ADAM_RIB")
    print("UNSUPPORTED_FIRSTNESS=PROHIBITED")
    print("TREE_TYPE_ASSERTION=PROHIBITED")
    print("PROPOSED_DISPOSITIONS=include_assertive,include_qualified,include_qualified")
    print(f"PROPOSAL_STATUS={proposal['status']}")
    print(f"CURRENT_EVIDENCE_GATE={manifest['evidence_gate_status']}")
    print(f"AUTOMATIC_EVIDENCE_APPROVAL={manifest['automatic_evidence_approval']}")
    print("HUMAN_EVIDENCE_APPROVAL=PENDING")
    print(f"LIVE_PROVIDER_EXECUTION={manifest['live_provider_execution']}")
    print(f"OUTPUT={Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
