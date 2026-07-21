"""One guarded Gemini production-TTS validation request; never retries/falls back."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(r"C:\SIRAJ\Workspace\first-project")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.application.local_video_production.audio_mastering_v1 import master_audio
from src.application.local_video_production.gemini_speech_provider_v1 import GeminiTTSError, GeminiTTSSpeechProvider
from src.application.local_video_production.production_tts_v1 import TTSSegmentRequest, inspect_pcm_wav
from src.application.local_video_production.voice_cast_v2 import GEMINI_PRIMARY_MODEL, PRIMARY_VOICE_ID
from src.application.local_video_production.voice_provider_v1 import atomic_write_json, file_sha256


def _status(error: GeminiTTSError) -> str:
    if "QUOTA" in error.code or "RATE" in error.code: return "BLOCKED_BY_QUOTA"
    if "API_KEY" in error.code or "PERMISSION" in error.code: return "BLOCKED_BY_KEY"
    if "MODEL" in error.code: return "MODEL_UNAVAILABLE"
    return "FAIL"


def main() -> int:
    if os.environ.get("SIRAJ_ALLOW_GEMINI_PRODUCTION_TTS", "").strip() != "YES":
        raise RuntimeError("GEMINI_PRODUCTION_TTS_NOT_AUTHORIZED")
    output_root = PROJECT_ROOT / "working" / "production-tts-gemini"
    raw = output_root / "gemini-tts-primary-raw.wav"
    final = output_root / "gemini-tts-primary-mastered.wav"
    mastering_report = output_root / "gemini-tts-primary-mastering.json"
    report_path = output_root / "gemini-tts-primary-live-report.json"
    request = TTSSegmentRequest("gemini-tts-live-primary-v1", "بغداد مدينة العلم.", "ar", GEMINI_PRIMARY_MODEL, PRIMARY_VOICE_ID, 1.0, "اقرأ بالعربية الفصحى بوضوح وهدوء.", "wav", 24000)
    try:
        GeminiTTSSpeechProvider().synthesize_segment(request, raw)
        raw_info = inspect_pcm_wav(raw)
        result = master_audio(PROJECT_ROOT, str(raw.relative_to(PROJECT_ROOT)), str(final.relative_to(PROJECT_ROOT)), str(mastering_report.relative_to(PROJECT_ROOT)))
        if result.status != "VALID": raise RuntimeError("MASTERING_INVALID")
        final_info = inspect_pcm_wav(final)
        report = {"status": "PASS", "provider": "gemini-tts-v1", "model": GEMINI_PRIMARY_MODEL, "voice": PRIMARY_VOICE_ID, "live_synthesis_requests": 1, "raw": str(raw), "raw_sha256": file_sha256(raw), "raw_sample_rate": raw_info["sample_rate"], "raw_channels": raw_info["channels"], "raw_duration_seconds": round(raw_info["duration_ms"] / 1000, 3), "mastered": str(final), "mastered_sha256": file_sha256(final), "mastered_sample_rate": final_info["sample_rate"], "mastered_channels": final_info["channels"], "mastered_duration_seconds": round(final_info["duration_ms"] / 1000, 3), "mastering_status": result.status}
        atomic_write_json(report_path, report); print(json.dumps(report, ensure_ascii=False, sort_keys=True)); return 0
    except GeminiTTSError as error:
        report = {"status": _status(error), "provider": "gemini-tts-v1", "model": GEMINI_PRIMARY_MODEL, "voice": PRIMARY_VOICE_ID, "live_synthesis_requests": 1, "error_code": error.code, "error_type": type(error).__name__}
        atomic_write_json(report_path, report); print(json.dumps(report, ensure_ascii=False, sort_keys=True)); return 2


if __name__ == "__main__": raise SystemExit(main())
