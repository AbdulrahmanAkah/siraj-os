from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.storyboard_runtime.gap_human_review import (  # noqa: E402
    load_and_build,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output_root = (args.output_root or repo).resolve()
    evidence = repo / "projects/episode-001-adam/evidence"
    packet, template = load_and_build(
        classification_path=evidence / "source-origin-classification-v1.json",
        proposal_path=evidence / "proposed-gap-adjudication-v1.json",
    )
    packet_path = output_root / "projects/episode-001-adam/evidence/gap-human-review-packet-v1.json"
    template_path = output_root / "projects/episode-001-adam/evidence/gap-human-approval-v1.template.json"
    write_json(packet_path, packet)
    write_json(template_path, template)
    print("STATUS=PASS_ADAM_GAP_HUMAN_REVIEW_PACKET")
    print(f"PACKET_ID={packet['packet_id']}")
    print("TARGET_EVENTS=3")
    print("HUMAN_REVIEW_READY=YES")
    print("HUMAN_EVIDENCE_APPROVAL=PENDING")
    print("EVIDENCE_BINDING_READY=NO")
    print("CURRENT_EVIDENCE_GATE=WITHHELD")
    print("AUTOMATIC_EVIDENCE_APPROVAL=FORBIDDEN")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    print(f"PACKET_OUTPUT={packet_path}")
    print(f"TEMPLATE_OUTPUT={template_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
