from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.episode_001_pipeline_adoption_v1 import (
    inspect_episode_001_adoption,
    run_episode_001_adoption_smoke_test,
)


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)

    module_text = (
        repo / "src/application/episode_001_pipeline_adoption_v1.py"
    ).read_text(encoding="utf-8")
    router_text = (
        repo / "src/application/production_resume_router_v1.py"
    ).read_text(encoding="utf-8")
    console_text = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "adopt_episode_001_for_pipeline",
        "LEGACY_FINAL_STORYBOARD_MASTER_V2_1",
        "20 generated videos" if False else "GENERATED_VIDEO",
        "legacy_files_preserved",
        "provider_requests",
    ):
        require(marker in module_text, "ADOPTION_MODULE_MARKER_MISSING:" + marker)
    require("ADOPT_EXISTING_EPISODE" in router_text, "ROUTER_ADOPTION_ACTION_MISSING")
    require("ربط الحلقة الأولى الحالية" in router_text, "ROUTER_ARABIC_ACTION_MISSING")
    require("adopt_episode_001_for_pipeline" in console_text, "CONSOLE_ADOPTION_NOT_WIRED")

    inspection = inspect_episode_001_adoption(repo)
    require(inspection.episode_exists, "EPISODE_001_NOT_FOUND")
    require(inspection.legacy_definition_exists, "LEGACY_DEFINITION_NOT_FOUND")
    require(inspection.legacy_script_exists, "LEGACY_SCRIPT_NOT_FOUND")
    require(inspection.legacy_storyboard_exists, "LEGACY_STORYBOARD_NOT_FOUND")
    require(inspection.legacy_evidence_exists, "LEGACY_EVIDENCE_NOT_FOUND")
    require(inspection.legacy_human_approval, "LEGACY_HUMAN_APPROVAL_NOT_PROVEN")

    smoke = run_episode_001_adoption_smoke_test(output / "smoke")
    require(smoke["status"] == "PASS", "ADOPTION_SMOKE_FAILED")
    require(smoke["images"] == 44, "IMAGE_COUNT_CHANGED")
    require(smoke["videos"] == 20, "VIDEO_COUNT_CHANGED")
    require(smoke["graphics"] == 6, "GRAPHICS_COUNT_CHANGED")
    require(smoke["provider_requests"] == 0, "PROVIDER_REQUEST_DETECTED")

    payload = {
        "status": "PASS",
        "release": "SIRAJ_EPISODE_001_PIPELINE_ADOPTION_V1",
        "inspection": inspection.as_dict(),
        "smoke": smoke,
    }
    (output / "audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
