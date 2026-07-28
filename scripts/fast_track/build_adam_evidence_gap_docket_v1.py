from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = SCRIPT_PATH.parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.application.storyboard_runtime.evidence_gap_closure import (  # noqa: E402
    AdamEvidenceGapClosureBuilder,
    write_gap_docket,
    write_gap_review_template,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Adam evidence gap closure docket without approving evidence."
    )
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--docket-output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--review-template-output",
        type=Path,
        default=None,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    episode_root = repo_root / "projects" / "episode-001-adam"
    docket_output = args.docket_output or (
        episode_root / "evidence" / "evidence-gap-closure-docket-v1.json"
    )
    review_output = args.review_template_output or (
        episode_root / "evidence" / "evidence-gap-review-v1.template.json"
    )

    docket = AdamEvidenceGapClosureBuilder().build_from_project(episode_root)
    write_gap_docket(docket_output, docket)
    write_gap_review_template(review_output, docket)
    manifest = docket.to_manifest()
    counts = manifest["counts"]

    print("STATUS=PASS_ADAM_EVIDENCE_GAP_DOCKET_BUILT")
    print(f"DOCKET_OUTPUT={docket_output}")
    print(f"REVIEW_TEMPLATE_OUTPUT={review_output}")
    print(f"DOCKET_ID={docket.docket_id}")
    print(f"TOTAL_UNCOVERED_EVENTS={counts['total_uncovered_events']}")
    print(f"FACTUAL_REVIEW_EVENTS={counts['factual_review_events']}")
    print(f"EDITORIAL_ONLY_EVENTS={counts['editorial_only_events']}")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
