"""Create local-only production storyboard artifacts from current subtitle outputs."""

from __future__ import annotations

from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(r"C:\SIRAJ\Workspace\first-project")
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from src.application.local_video_production.storyboard_generator_v1 import StoryboardRequest, generate_storyboard


def main() -> int:
    _, result, validation = generate_storyboard(StoryboardRequest(
        mastered_audio_path=PROJECT_ROOT / "working" / "production-tts-gemini" / "gemini-tts-primary-mastered.wav",
        subtitle_manifest_path=PROJECT_ROOT / "manifests" / "production-subtitles-v1.json",
        output_directory=PROJECT_ROOT / "working" / "storyboard-v1",
        manifest_path=PROJECT_ROOT / "manifests" / "production-storyboard-v1.json",
    ))
    if validation.status == "FAIL" or validation.quality_grade not in {"STRONG", "EXCELLENT"}:
        raise RuntimeError("STORYBOARD_PRODUCTION_VALIDATION_FAILED")
    print(result.status)
    print(result.manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
