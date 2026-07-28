from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _bootstrap_repo_root() -> Path:
    candidate = Path(__file__).resolve().parents[2]
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    return candidate


REPO_ROOT = _bootstrap_repo_root()

from src.application.storyboard_runtime.evidence_recovery import (  # noqa: E402
    AdamEvidenceKnowledgeRecovery,
    EvidenceRecoveryError,
    validate_recovered_manifest,
    write_recovered_evidence_knowledge,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recover existing Adam evidence metadata without approving evidence "
            "or opening the execution gate."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--validate-existing",
        action="store_true",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output = args.output or (
        repo_root
        / "projects"
        / "episode-001-adam"
        / "evidence"
        / "recovered-evidence-knowledge-v1.json"
    )

    try:
        if args.validate_existing:
            payload = json.loads(output.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise EvidenceRecoveryError("Recovered manifest must be an object.")
            validate_recovered_manifest(payload)
            recovered_id = payload["recovery_id"]
            normalized_count = payload["normalized_source_count"]
            review_count = payload["review_artifact_count"]
            status = payload["recovery_status"]
        else:
            recovered = AdamEvidenceKnowledgeRecovery().build(repo_root)
            write_recovered_evidence_knowledge(recovered, output)
            payload = recovered.to_manifest()
            validate_recovered_manifest(payload)
            recovered_id = recovered.recovery_id
            normalized_count = recovered.normalized_source_count
            review_count = recovered.review_artifact_count
            status = recovered.recovery_status

        print("STATUS=PASS_RECOVERED_EVIDENCE_KNOWLEDGE")
        print(f"OUTPUT={output}")
        print(f"RECOVERY_ID={recovered_id}")
        print(f"RECOVERY_STATUS={status}")
        print(f"NORMALIZED_SOURCE_COUNT={normalized_count}")
        print(f"REVIEW_ARTIFACT_COUNT={review_count}")
        print("CURRENT_EVIDENCE_GATE=WITHHELD")
        print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
        print("RAW_SOURCE_TEXT_COPIED=NO")
        print("LIVE_PROVIDER_EXECUTION=BLOCKED")
        return 0
    except (EvidenceRecoveryError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(
            f"STATUS=FAIL {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
