from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.storyboard_runtime.production_research_policy import (  # noqa: E402
    AdamResearchProductionBuilder,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--policy-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()

    output_root = args.output_root or args.repo_root
    built = AdamResearchProductionBuilder(
        args.repo_root,
        policy_root=args.policy_root,
    ).build_all()
    paths = write_outputs(output_root, built)

    review = built["review_pack"]
    filler = built["filler_plan"]
    recitation = built["recitation_plan"]
    candidate_count = sum(
        item["candidate_record_count"] for item in review["events"]
    )

    print("STATUS=PASS_ADAM_RESEARCH_PRODUCTION_PACK_BUILT")
    print(f"REVIEW_PACK_OUTPUT={paths['review_pack']}")
    print(f"NOTEBOOKLM_PROMPTS_OUTPUT={paths['notebooklm_prompts']}")
    print(f"FILLER_PLAN_OUTPUT={paths['filler_plan']}")
    print(f"RECITATION_PLAN_OUTPUT={paths['recitation_plan']}")
    print(f"REVIEW_PACK_ID={review['pack_id']}")
    print("TARGETED_FACTUAL_EVENTS=3")
    print(f"AUTOMATED_PREFILTER_CANDIDATES={candidate_count}")
    print(f"FILLER_FRAME_COUNT={len(filler['frames'])}")
    print(f"RECITATION_CUE_CANDIDATES={len(recitation['cues'])}")
    print("TEMPORARY_HADITH_AUTHORITY=DORAR_AL_SUNNIYYAH")
    print("MUSIC_POLICY=PROHIBITED_GLOBALLY")
    print("RECITATION_AUDIO_MODE=QURAN_ONLY_EXCLUSIVE_AUDIO")
    print("PREFERRED_RECITER=MISHARY_RASHID_ALAFASY")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
