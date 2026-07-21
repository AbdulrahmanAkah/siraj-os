"""Record the Storyboard Generator v1 milestone after local validation."""

from __future__ import annotations

from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from scripts.project_progress.recorder import record_milestone


def main() -> int:
    record_milestone(
        project_progress_path=REPOSITORY / "PROJECT_PROGRESS.md",
        ledger_path=REPOSITORY / "docs" / "execution" / "project-milestones.json",
        milestone_id="2026-07-22-storyboard-generator-v1",
        title_ar="Complete Cinematic Storyboard Generator v1",
        status="COMPLETED",
        summary_ar="Deterministic narrative, scene, beat, shot, prompt, continuity, asset, subtitle-safe, and render-ready storyboard planning completed without media generation.",
        next_action_ar="Resolve planned visual asset requirements before a final episode render.",
        changed_files=[
            "src/application/local_video_production/storyboard_generator_v1.py",
            "src/application/local_video_production/subtitles_v1.py",
            "src/application/local_video_production/__init__.py",
            "scripts/fast_track/run_production_storyboard_v1.py",
            "scripts/fast_track/record_storyboard_generator_v1.py",
            "tests/integration/test_storyboard_generator_v1.py",
            "tests/integration/test_subtitles_v1.py",
            "PROJECT_PROGRESS.md",
            "docs/execution/project-milestones.json",
        ],
        metadata={
            "schema_version": "siraj-production-storyboard-generator-v1",
            "local_production_status": "PASS",
            "render_readiness": "PASS",
            "media_generation": "NOT_EXECUTED",
            "quality_gate": "STRONG_OR_EXCELLENT_REQUIRED",
        },
    )
    print("STORYBOARD_MILESTONE_RECORDED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
