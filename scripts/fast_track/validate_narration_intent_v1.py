from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_repo_root())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from src.application.storyboard_runtime.narration_intent import (
        load_and_validate_bundle,
        write_validation_manifest,
    )

    manifest = load_and_validate_bundle(
        narration_policy_path=repo / "config/historical_narration_policy_v1.json",
        creator_intent_path=repo / "config/creator_editorial_intent_v1.json",
        adam_direction_path=(
            repo
            / "projects/episode-001-adam/evidence/editorial-direction-v1.json"
        ),
        event_map_path=repo / "projects/episode-001-adam/editorial/event-map.json",
    )
    if args.output is not None:
        write_validation_manifest(args.output, manifest)

    print("STATUS=PASS_NARRATION_INTENT_BUNDLE")
    print(f"BUNDLE_ID={manifest['bundle_id']}")
    print("HISTORICAL_NARRATION_POLICY=siraj-historical-narration-policy-v1")
    print("CREATOR_EDITORIAL_INTENT=siraj-creator-editorial-intent-v1")
    print("ADAM_EDITORIAL_DIRECTION=siraj-adam-editorial-direction-v1")
    print("UNSUPPORTED_FIRSTNESS=PROHIBITED_WITHOUT_DIRECT_SOUND_EVIDENCE")
    print("ISRAILIYYAT=NARRATE_ONLY_WITH_EXPLICIT_LABEL")
    print("SUPPORTED_SYNTHESIS=ALLOWED_WITH_PREMISE_TRACE")
    print("SOURCE_NAMES_IN_NARRATION=SPARING")
    print("TREE_TYPE_ASSERTION=PROHIBITED")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
