"""Record the completed Subtitle Generation & Timing v1 milestone."""

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
        milestone_id="2026-07-22-subtitle-generation-timing-v1",
        title_ar="Complete Subtitle Generation and Timing v1",
        status="COMPLETED",
        summary_ar=(
            "Deterministic Arabic subtitle segmentation, mastered-audio timing, "
            "SRT/VTT/ASS exports, validation, dialogue metadata, cache, and "
            "ASS render readiness completed with a local production artifact."
        ),
        next_action_ar="Use the subtitle manifest in the first episode render manifest.",
        changed_files=[
            "src/application/local_video_production/subtitles_v1.py",
            "src/application/local_video_production/__init__.py",
            "scripts/fast_track/run_production_subtitles_v1.py",
            "scripts/fast_track/record_subtitle_generation_timing_v1.py",
            "tests/integration/test_subtitles_v1.py",
            "tests/integration/test_render_adapter_v2.py",
            "PROJECT_PROGRESS.md",
            "docs/execution/project-milestones.json",
        ],
        metadata={
            "schema_version": "siraj-production-subtitles-v1",
            "exports": ["SRT", "WebVTT", "ASS"],
            "timing_sources": ["TTS_METADATA_EXACT", "MASTERED_AUDIO_ESTIMATED"],
            "local_production_status": "PASS",
            "render_integration": "READY",
        },
    )
    print("SUBTITLE_MILESTONE_RECORDED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
