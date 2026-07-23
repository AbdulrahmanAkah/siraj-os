"""Create the evidence-only audit of pre-existing quality-gate images."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path: sys.path.insert(0, str(REPOSITORY))

from src.application.local_video_production.visual_audit_v1 import audit_previous_image_generation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    root = Path(args.project_root)
    report = audit_previous_image_generation(root, root / "manifests" / "previous-image-generation-audit-v1.json")
    audit_previous_image_generation(root, root / "working" / "visual-provider-v1" / "previous-image-generation-audit-v1.json")
    print(report["previous_images_generation_method"])
    return 0


if __name__ == "__main__": raise SystemExit(main())
