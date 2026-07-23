"""Generate the approved Gemini Arabic TTS audition set only.

This is a standalone audition tool.  It is not registered as a SIRAJ
production provider and it makes at most one synthesis request per voice.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import wave

from google import genai
from google.genai import types


MODEL_REFERENCE = "gemini-2.5-flash-preview-tts"
OUTPUT_ROOT = Path(r"C:\SIRAJ\Workspace\first-project\working\voice-samples\gemini-arabic-v1")
MANIFEST_PATH = Path(r"C:\SIRAJ\Workspace\first-project\manifests\gemini-arabic-voice-samples-v1.json")
TEXT = "في قلب بغداد، وعلى ضفاف دجلة، ازدهرت مدينة لم تكن مجرد عاصمة لإمبراطورية واسعة، بل مركزًا للعلم والترجمة والفلسفة."
STYLE = (
    "اقرأ النص التالي بالعربية الفصحى بصوت رجل في منتصف العمر، دافئ وعميق، "
    "بأسلوب وثائقي هادئ وموثوق، واضح المخارج، تعبيري دون مبالغة، بسرعة متوسطة "
    "ووقفات طبيعية. تجنب الأسلوب الإعلاني أو الإذاعي المصطنع. اقرأ النص فقط كما هو."
)
VOICES = (
    ("01-Charon.wav", "Charon", 8),
    ("02-Rasalgethi.wav", "Rasalgethi", 8),
    ("03-Alnilam.wav", "Alnilam", 8),
    ("04-Iapetus.wav", "Iapetus", 8),
    ("05-Schedar.wav", "Schedar", 7),
    ("06-Enceladus.wav", "Enceladus", 7),
)


def _redact(value: object) -> str:
    detail = str(value or "").replace("\r", " ").replace("\n", " ")[-500:]
    return re.sub(r"AIza[0-9A-Za-z_-]{12,}", "[REDACTED_API_KEY]", detail)


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def _sample_rate_from_mime(mime_type: str | None) -> int:
    match = re.search(r"rate=(\d+)", str(mime_type or ""), flags=re.IGNORECASE)
    return int(match.group(1)) if match else 24000


def _audio_part(response: object) -> tuple[bytes, str | None]:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise ValueError("GEMINI_TTS_NO_CANDIDATES")
    parts = getattr(getattr(candidates[0], "content", None), "parts", None) or []
    for part in parts:
        inline_data = getattr(part, "inline_data", None)
        data = getattr(inline_data, "data", None) if inline_data is not None else None
        if data:
            return bytes(data), getattr(inline_data, "mime_type", None)
    raise ValueError("GEMINI_TTS_AUDIO_PART_MISSING")


def _write_wav(path: Path, audio: bytes, mime_type: str | None) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio[:4] == b"RIFF":
        path.write_bytes(audio)
    else:
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(_sample_rate_from_mime(mime_type))
            handle.writeframes(audio)
    with wave.open(str(path), "rb") as handle:
        if handle.getcomptype() != "NONE" or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError("GEMINI_TTS_WAV_FORMAT_INVALID")
        frame_count = handle.getnframes()
        sample_rate = handle.getframerate()
        if frame_count <= 0:
            raise ValueError("GEMINI_TTS_WAV_HAS_NO_SAMPLES")
    return {
        "duration_seconds": round(frame_count / sample_rate, 3),
        "sample_rate": sample_rate,
        "channels": 1,
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }


def _is_global_blocker(error: Exception) -> bool:
    message = f"{type(error).__name__}:{error}".lower()
    return any(token in message for token in ("api key", "unauthenticated", "permission", "billing", "quota", "resourceexhausted", "rate limit"))


def main() -> int:
    if os.environ.get("SIRAJ_ALLOW_GEMINI_TTS_SAMPLES", "").strip() != "YES":
        raise RuntimeError("GEMINI_TTS_SAMPLES_NOT_AUTHORIZED")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY_MISSING")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=api_key)
    results: list[dict[str, object]] = []
    global_blocker = False

    for filename, voice_name, prior_score in VOICES:
        output_path = OUTPUT_ROOT / filename
        entry: dict[str, object] = {
            "voice_name": voice_name,
            "prior_score": prior_score,
            "status": "NOT_ATTEMPTED_GLOBAL_BLOCKER" if global_blocker else "PENDING",
            "output": str(output_path),
            "duration_seconds": None,
            "sample_rate": None,
            "channels": None,
            "sha256": None,
            "error": None,
        }
        if not global_blocker:
            try:
                response = client.models.generate_content(
                    model=MODEL_REFERENCE,
                    contents=f"{STYLE}\n\nالنص:\n{TEXT}",
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            language_code="ar",
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                            ),
                        ),
                    ),
                )
                entry.update(status="PASS", **_write_wav(output_path, *_audio_part(response)))
            except Exception as error:
                entry["status"] = "FAIL"
                entry["error"] = f"{type(error).__name__}:{_redact(error)}"
                global_blocker = _is_global_blocker(error)
        results.append(entry)
        _atomic_json(MANIFEST_PATH, {
            "schema_version": "siraj-gemini-arabic-voice-samples-v1",
            "model_reference": MODEL_REFERENCE,
            "request_policy": "ONE_SYNTHESIS_REQUEST_PER_VOICE_NO_RETRIES",
            "text_sha256": sha256(TEXT.encode("utf-8")).hexdigest(),
            "samples": results,
        })

    summary = {
        "manifest": str(MANIFEST_PATH),
        "attempted_synthesis_requests": sum(1 for item in results if item["status"] in {"PASS", "FAIL"}),
        "successful_files": sum(1 for item in results if item["status"] == "PASS"),
        "failed_files": sum(1 for item in results if item["status"] == "FAIL"),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["failed_files"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
