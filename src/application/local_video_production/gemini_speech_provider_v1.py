"""Official Gemini TTS provider for the production narration adapter."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable
import wave

from .production_tts_v1 import SegmentTTSProvider, TTSSegmentRequest, inspect_pcm_wav
from .voice_cast_v2 import APPROVED_GEMINI_VOICES, GEMINI_FALLBACK_MODEL, GEMINI_PRIMARY_MODEL, GEMINI_TTS_PROVIDER_ID, PRIMARY_VOICE_ID


GEMINI_TTS_DEFAULT_SAMPLE_RATE = 24000


@dataclass(frozen=True)
class GeminiTTSQuotaPolicy:
    requests_per_minute: int = 3
    requests_per_day: int = 10
    tokens_per_minute: int = 10000


@dataclass(frozen=True)
class GeminiTTSConfiguration:
    api_key_environment_variable: str = "GEMINI_API_KEY"
    primary_model: str = GEMINI_PRIMARY_MODEL
    fallback_model: str = GEMINI_FALLBACK_MODEL
    timeout_seconds: float = 90.0
    sample_rate_hertz: int = GEMINI_TTS_DEFAULT_SAMPLE_RATE
    quota_policy: GeminiTTSQuotaPolicy = field(default_factory=GeminiTTSQuotaPolicy)


def load_gemini_tts_configuration(environment: dict[str, str] | None = None) -> GeminiTTSConfiguration:
    """Load operational limits without serializing or exposing the API key."""
    values = environment if environment is not None else os.environ
    def positive(name: str, default: int) -> int:
        value = int(values.get(name, str(default)))
        if value < 1: raise ValueError(f"GEMINI_TTS_LIMIT_INVALID:{name}")
        return value
    return GeminiTTSConfiguration(
        primary_model=values.get("SIRAJ_GEMINI_TTS_PRIMARY_MODEL", GEMINI_PRIMARY_MODEL),
        fallback_model=values.get("SIRAJ_GEMINI_TTS_FALLBACK_MODEL", GEMINI_FALLBACK_MODEL),
        quota_policy=GeminiTTSQuotaPolicy(
            requests_per_minute=positive("SIRAJ_GEMINI_TTS_RPM", 3),
            requests_per_day=positive("SIRAJ_GEMINI_TTS_RPD", 10),
            tokens_per_minute=positive("SIRAJ_GEMINI_TTS_TPM", 10000),
        ),
    )


def gemini_tts_manifest(configuration: GeminiTTSConfiguration | None = None) -> dict[str, object]:
    configuration = configuration or GeminiTTSConfiguration()
    return {
        "schema_version": "siraj-production-gemini-tts-v1",
        "status": "VALID_LOCAL_CONFIGURATION",
        "active_provider": GEMINI_TTS_PROVIDER_ID,
        "active_model": configuration.primary_model,
        "fallback_model": configuration.fallback_model,
        "primary_voice": PRIMARY_VOICE_ID,
        "supporting_voices": [voice for voice in APPROVED_GEMINI_VOICES if voice != PRIMARY_VOICE_ID],
        "quota_policy": {"requests_per_minute": configuration.quota_policy.requests_per_minute, "requests_per_day": configuration.quota_policy.requests_per_day, "tokens_per_minute": configuration.quota_policy.tokens_per_minute},
        "live_validation_status": "NOT_RUN",
        "mastering_status": "CONFIGURED_BY_REQUEST",
        "cache_status": "ENABLED_IN_ORCHESTRATOR",
    }


class GeminiTTSError(RuntimeError):
    code = "GEMINI_TTS_PROVIDER_ERROR"
    retryable = False
    fallback_eligible = False
    fatal_configuration_error = False

    def __init__(self, detail: str = "") -> None:
        super().__init__(self.code if not detail else f"{self.code}:{redact_sensitive(detail)}")


class GeminiTTSMissingApiKeyError(GeminiTTSError):
    code = "GEMINI_TTS_MISSING_API_KEY"
    fatal_configuration_error = True


class GeminiTTSInvalidApiKeyError(GeminiTTSError):
    code = "GEMINI_TTS_INVALID_API_KEY"
    fatal_configuration_error = True


class GeminiTTSPermissionDeniedError(GeminiTTSError):
    code = "GEMINI_TTS_PERMISSION_DENIED"
    fatal_configuration_error = True


class GeminiTTSModelUnavailableError(GeminiTTSError):
    code = "GEMINI_TTS_MODEL_UNAVAILABLE"
    fallback_eligible = True


class GeminiTTSInvalidModelError(GeminiTTSError):
    code = "GEMINI_TTS_INVALID_MODEL"
    fatal_configuration_error = True


class GeminiTTSInvalidVoiceError(GeminiTTSError):
    code = "GEMINI_TTS_INVALID_VOICE"
    fatal_configuration_error = True


class GeminiTTSInvalidRequestError(GeminiTTSError):
    code = "GEMINI_TTS_INVALID_REQUEST"
    fatal_configuration_error = True


class GeminiTTSQuotaExhaustedError(GeminiTTSError):
    code = "GEMINI_TTS_QUOTA_EXHAUSTED"
    fallback_eligible = True


class GeminiTTSDailyQuotaExhaustedError(GeminiTTSError):
    code = "GEMINI_TTS_DAILY_QUOTA_EXHAUSTED"
    fallback_eligible = True


class GeminiTTSRateLimitedError(GeminiTTSError):
    code = "GEMINI_TTS_RATE_LIMITED"
    fallback_eligible = True


class GeminiTTSTimeoutError(GeminiTTSError):
    code = "GEMINI_TTS_TIMEOUT"
    retryable = True
    fallback_eligible = True


class GeminiTTSConnectionError(GeminiTTSError):
    code = "GEMINI_TTS_CONNECTION_ERROR"
    retryable = True
    fallback_eligible = True


class GeminiTTSServiceUnavailableError(GeminiTTSError):
    code = "GEMINI_TTS_SERVICE_UNAVAILABLE"
    retryable = True
    fallback_eligible = True


class GeminiTTSMalformedAudioError(GeminiTTSError):
    code = "GEMINI_TTS_MALFORMED_AUDIO_RESPONSE"
    fallback_eligible = True


class GeminiTTSEmptyAudioError(GeminiTTSError):
    code = "GEMINI_TTS_EMPTY_AUDIO_RESPONSE"
    fallback_eligible = True


class GeminiTTSUnsupportedOutputError(GeminiTTSError):
    code = "GEMINI_TTS_UNSUPPORTED_OUTPUT"
    fallback_eligible = True


GEMINI_TTS_RETRYABLE_ERRORS = (GeminiTTSTimeoutError, GeminiTTSConnectionError, GeminiTTSServiceUnavailableError)


def redact_sensitive(value: object) -> str:
    detail = str(value or "").replace("\r", " ").replace("\n", " ")[-500:]
    return re.sub(r"AIza[0-9A-Za-z_-]{12,}", "[REDACTED_API_KEY]", detail)


def classify_gemini_tts_error(error: Exception) -> GeminiTTSError:
    text = f"{type(error).__name__}:{error}".lower()
    detail = redact_sensitive(error)
    if "api key" in text and ("missing" in text or "required" in text): return GeminiTTSMissingApiKeyError(detail)
    if "api key" in text or "unauthenticated" in text or "invalid key" in text: return GeminiTTSInvalidApiKeyError(detail)
    if "permission" in text or "forbidden" in text: return GeminiTTSPermissionDeniedError(detail)
    if "requestsperday" in text or "daily" in text and "quota" in text: return GeminiTTSDailyQuotaExhaustedError(detail)
    if "requestsperminute" in text or "rate limit" in text or "429" in text: return GeminiTTSRateLimitedError(detail)
    if "quota" in text or "resourceexhausted" in text: return GeminiTTSQuotaExhaustedError(detail)
    if "model" in text and ("not found" in text or "unavailable" in text): return GeminiTTSModelUnavailableError(detail)
    if "model" in text and ("invalid" in text or "unsupported" in text): return GeminiTTSInvalidModelError(detail)
    if "timeout" in text or "deadline" in text: return GeminiTTSTimeoutError(detail)
    if "connection" in text or "network" in text: return GeminiTTSConnectionError(detail)
    if "unavailable" in text or "503" in text or "500" in text: return GeminiTTSServiceUnavailableError(detail)
    return GeminiTTSError(detail)


class GeminiTTSRateLimitGuard:
    """In-process conservative guard; server quotas remain authoritative."""
    def __init__(self, policy: GeminiTTSQuotaPolicy, clock: Callable[[], float] = time.time) -> None:
        self.policy, self.clock = policy, clock
        self._requests: dict[str, deque[tuple[float, int]]] = {}

    def acquire(self, model: str, text: str) -> None:
        now = self.clock()
        entries = self._requests.setdefault(model, deque())
        while entries and now - entries[0][0] >= 86400: entries.popleft()
        if len(entries) >= self.policy.requests_per_day: raise GeminiTTSDailyQuotaExhaustedError("LOCAL_DAILY_LIMIT")
        minute = [item for item in entries if now - item[0] < 60]
        if len(minute) >= self.policy.requests_per_minute: raise GeminiTTSRateLimitedError("LOCAL_RPM_LIMIT")
        estimated_tokens = max(1, len(text) // 3)
        if sum(item[1] for item in minute) + estimated_tokens > self.policy.tokens_per_minute: raise GeminiTTSRateLimitedError("LOCAL_TPM_LIMIT")
        entries.append((now, estimated_tokens))


def validate_gemini_tts_request(request: TTSSegmentRequest, configuration: GeminiTTSConfiguration) -> None:
    if not request.text.strip(): raise GeminiTTSInvalidRequestError("TEXT_REQUIRED")
    if request.voice_id not in APPROVED_GEMINI_VOICES: raise GeminiTTSInvalidVoiceError(request.voice_id)
    if request.model not in {configuration.primary_model, configuration.fallback_model}: raise GeminiTTSInvalidModelError(request.model)
    if request.response_format.lower() != "wav": raise GeminiTTSUnsupportedOutputError("SIRAJ_OUTPUT_MUST_BE_WAV")
    if request.sample_rate <= 0 or not request.language.lower().startswith("ar"): raise GeminiTTSInvalidRequestError("ARABIC_SAMPLE_RATE_REQUIRED")


def _response_audio(response: Any) -> tuple[bytes, str | None]:
    candidates = getattr(response, "candidates", None) or []
    parts = getattr(getattr(candidates[0], "content", None), "parts", None) if candidates else None
    if not parts: raise GeminiTTSEmptyAudioError("NO_AUDIO_CANDIDATE")
    for part in parts:
        inline = getattr(part, "inline_data", None)
        data = getattr(inline, "data", None) if inline else None
        if data: return bytes(data), getattr(inline, "mime_type", None)
    raise GeminiTTSEmptyAudioError("AUDIO_PART_MISSING")


def _rate_from_mime(mime_type: str | None) -> int:
    match = re.search(r"rate=(\d+)", str(mime_type or ""), re.IGNORECASE)
    return int(match.group(1)) if match else GEMINI_TTS_DEFAULT_SAMPLE_RATE


class GeminiTTSSpeechProvider(SegmentTTSProvider):
    provider_id = GEMINI_TTS_PROVIDER_ID
    retryable_errors = GEMINI_TTS_RETRYABLE_ERRORS

    def __init__(self, configuration: GeminiTTSConfiguration | None = None, *, client: Any | None = None, types_module: Any | None = None, rate_guard: GeminiTTSRateLimitGuard | None = None) -> None:
        self.configuration = configuration or GeminiTTSConfiguration()
        self._client, self._types = client, types_module
        self._guard = rate_guard or GeminiTTSRateLimitGuard(self.configuration.quota_policy)

    def _client_and_types(self) -> tuple[Any, Any]:
        if self._client is not None and self._types is not None: return self._client, self._types
        key = os.environ.get(self.configuration.api_key_environment_variable, "").strip()
        if not key: raise GeminiTTSMissingApiKeyError()
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise GeminiTTSError("GOOGLE_GENAI_SDK_NOT_INSTALLED") from error
        self._client, self._types = genai.Client(api_key=key), types
        return self._client, self._types

    def synthesize_segment(self, request: TTSSegmentRequest, output_path: Path) -> None:
        validate_gemini_tts_request(request, self.configuration)
        self._guard.acquire(request.model, request.text)
        client, types = self._client_and_types()
        style = request.instructions or "اقرأ بالعربية الفصحى بوضوح وبوقفات طبيعية."
        try:
            config_values: dict[str, Any] = {
                "response_modalities": ["AUDIO"],
                "speech_config": types.SpeechConfig(language_code="ar", voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=request.voice_id))),
            }
            if hasattr(types, "HttpOptions"):
                config_values["http_options"] = types.HttpOptions(timeout=int(self.configuration.timeout_seconds * 1000))
            response = client.models.generate_content(
                model=request.model,
                contents=f"{style}\n\nالنص:\n{request.text}",
                config=types.GenerateContentConfig(**config_values),
            )
            audio, mime_type = _response_audio(response)
        except GeminiTTSError:
            raise
        except Exception as error:
            raise classify_gemini_tts_error(error) from error
        if not audio: raise GeminiTTSEmptyAudioError()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix=".wav", delete=False) as handle:
            temporary = Path(handle.name)
            if audio[:4] == b"RIFF": handle.write(audio)
            else:
                with wave.open(handle, "wb") as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(_rate_from_mime(mime_type)); wav.writeframes(audio)
        try:
            info = inspect_pcm_wav(temporary)
            if info["frame_count"] <= 0: raise GeminiTTSEmptyAudioError("NO_AUDIO_FRAMES")
            temporary.replace(output_path)
        except GeminiTTSError: raise
        except Exception as error: raise GeminiTTSMalformedAudioError(type(error).__name__) from error
        finally: temporary.unlink(missing_ok=True)
