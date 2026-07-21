"""Write the non-secret production TTS policy manifest without a live call."""

from __future__ import annotations

from pathlib import Path
import sys
import json


REPO = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(r"C:\SIRAJ\Workspace\first-project")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.application.local_video_production.gemini_speech_provider_v1 import gemini_tts_manifest, load_gemini_tts_configuration
from src.application.local_video_production.voice_cast_v2 import voice_cast_to_dict
from src.application.local_video_production.voice_provider_v1 import atomic_write_json


def main() -> int:
    output = PROJECT_ROOT / "manifests" / "production-tts-adapter-v1.json"
    manifest = gemini_tts_manifest(load_gemini_tts_configuration())
    manifest["voice_cast"] = voice_cast_to_dict()
    live_report = PROJECT_ROOT / "working" / "production-tts-gemini" / "gemini-tts-primary-live-report.json"
    if live_report.is_file():
        live = json.loads(live_report.read_text(encoding="utf-8-sig"))
        manifest["live_validation_status"] = live.get("status", "UNKNOWN")
        manifest["live_validation_report"] = str(live_report)
        manifest["mastering_status"] = live.get("mastering_status", "NOT_RUN")
    atomic_write_json(output, manifest)
    print("PRODUCTION_TTS_MANIFEST_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
