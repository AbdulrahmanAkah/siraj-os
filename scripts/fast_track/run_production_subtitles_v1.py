"""Generate Subtitle Generation & Timing v1 artifacts from an existing mastered WAV."""

from __future__ import annotations

from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(r"C:\SIRAJ\Workspace\first-project")
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from src.application.local_video_production.subtitles_v1 import (
    SubtitleRequest,
    TranscriptSegment,
    generate_subtitles,
)


def main() -> int:
    audio = PROJECT_ROOT / "working" / "production-tts-gemini" / "gemini-tts-primary-mastered.wav"
    request = SubtitleRequest(
        mastered_audio_path=audio,
        transcript="بغداد مدينة العلم.",
        transcript_segments=(TranscriptSegment(text="بغداد مدينة العلم.", speaker_id="narrator-primary", speaker_name="الراوي", role="PRIMARY_NARRATOR", voice_id="Alnilam", scene_id="subtitle-production-local-v1"),),
        output_directory=PROJECT_ROOT / "working" / "subtitles-v1",
        manifest_path=PROJECT_ROOT / "manifests" / "production-subtitles-v1.json",
    )
    _, result, validation = generate_subtitles(request)
    if validation.status == "FAIL":
        raise RuntimeError("SUBTITLE_PRODUCTION_VALIDATION_FAILED")
    print(result.status)
    print(result.manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
