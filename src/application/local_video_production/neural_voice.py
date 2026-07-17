"""Policy-gated Azure Neural TTS audition support for documentary v4.

This module deliberately contains no fallback to eSpeak or Windows SAPI.  A
production audition is either made by an explicitly authorised neural provider
or is reported as blocked.  Credential resolution is injected from the central
configuration layer, so this adapter never reads the environment itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace as replace_dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata
import wave
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.application.ai_provider_openai_compatible import (
    CredentialReference,
    ExternalAIExecutionPolicy,
)
from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id


VOICE_AUDITION_SCHEMA = "siraj-voice-audition-report-v4"
AZURE_NEURAL_PROVIDER = "AZURE_NEURAL_TTS"
_FORBIDDEN_PRODUCTION_PROVIDERS = {"ESPEAK", "ESPEAK_NG", "WINDOWS_SYSTEM_SPEECH", "SYSTEM_SPEECH"}
_BANNED_NARRATION_METADATA = (
    "historical fact number",
    "this fact is documented",
    "supported by source",
    "claim id",
    "source id",
)
_ARABIC_AUDITION_TEXT = (
    "في قلب العراق، وعلى ضفاف دجلة، وُلدت بغداد؛ مدينةٌ لم تكن مجرد عاصمة، بل بوابةً إلى المعرفة والسلطة. "
    "وفي القرن الثامن الميلادي، أسّس الخليفة أبو جعفر المنصور عاصمةً جديدةً للدولة العباسية، لتبدأ منها حكايةٌ غيّرت وجه التاريخ."
)
_AUDITION_HOOK = "في قلب العراق، وعلى ضفاف دجلة، وُلدت بغداد؛"
_AUDITION_BODY = (
    "مدينةٌ لم تكن مجرد عاصمة، بل بوابةً إلى المعرفة والسلطة. "
    "وفي القرن الثامن الميلادي، أسّس الخليفة أبو جعفر المنصور عاصمةً جديدةً للدولة العباسية، "
    "لتبدأ منها حكايةٌ غيّرت وجه التاريخ."
)


class NeuralVoiceError(RuntimeError):
    """Sanitized provider or quality-gate failure."""


class CredentialResolver(Protocol):
    def resolve(self, reference: CredentialReference) -> str | None: ...


class NeuralVoiceProvider(Protocol):
    provider_id: str

    def synthesize(self, request: "NeuralVoiceRequest") -> "NeuralVoiceResult": ...


@dataclass(frozen=True)
class AzureNeuralVoiceConfig:
    endpoint: str
    subscription_key_reference: CredentialReference
    region: str | None = None
    timeout_seconds: float = 30.0
    output_format: str = "riff-24khz-16bit-mono-pcm"
    provider_id: str = AZURE_NEURAL_PROVIDER


@dataclass(frozen=True)
class NeuralVoiceRequest:
    text: str
    output_wav: str
    voice: str
    locale: str = "ar-SA"
    speaking_rate: str = "-15%"
    pitch: str = "+0Hz"
    sample_rate_hz: int = 24_000
    pronunciation_dictionary: dict[str, str] | None = None
    hook_text: str | None = None
    body_text: str | None = None
    emphasis_level: str = "moderate"
    hook_break_ms: int = 280
    body_rate: str | None = None


@dataclass(frozen=True)
class NeuralVoiceResult:
    provider: str
    model: str
    voice: str
    locale: str
    speaking_rate: str
    pitch: str
    sample_rate_hz: int
    output_wav: str
    duration_ms: int
    sha256: str
    response_metadata: dict[str, str] = field(default_factory=dict)


def normalize_arabic_for_tts(text: str, pronunciation_dictionary: dict[str, str] | None = None) -> str:
    """Apply only explicit, reviewable Arabic pronunciation substitutions."""

    normalized = unicodedata.normalize("NFC", text).replace("ـ", "")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    replacements = {
        "بغداد": "بَغْداد",
        "دجلة": "دِجْلَة",
        "المنصور": "المَنْصور",
        "أبو جعفر": "أبو جَعْفَر",
        "762": "سبعمئة واثنتان وستون",
    }
    replacements.update(pronunciation_dictionary or {})
    for source, spoken in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalized.replace(source, spoken)
    # Explicit punctuation creates prosodic pauses without inventing narration.
    normalized = normalized.replace("،", "، ").replace(". ", ". ")
    return re.sub(r"\s+", " ", normalized).strip()


def validate_wav_audio(path: Path) -> tuple[int, int, int]:
    """Reject empty RIFF headers, empty data chunks, and silent PCM payloads."""

    if not path.is_file() or path.stat().st_size < 1_000:
        raise NeuralVoiceError("NEURAL_VOICE_WAV_TOO_SMALL")
    with wave.open(str(path), "rb") as audio:
        frames, rate, width = audio.getnframes(), audio.getframerate(), audio.getsampwidth()
        data = audio.readframes(frames)
    if frames <= 0 or rate <= 0 or width <= 0 or not data:
        raise NeuralVoiceError("NEURAL_VOICE_WAV_EMPTY_DATA_CHUNK")
    if not any(data):
        raise NeuralVoiceError("NEURAL_VOICE_WAV_SILENT_DATA_CHUNK")
    return frames, rate, round(frames * 1_000 / rate)


def _duration_ms(path: Path) -> int:
    return validate_wav_audio(path)[2]


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_audition_wav(path: Path, ffmpeg: str | None = None) -> NeuralVoiceResult | None:
    """Trim edge silence and produce a stable, spoken-word loudness target."""

    executable = ffmpeg or shutil.which("ffmpeg")
    if not executable:
        raise NeuralVoiceError("FFMPEG_REQUIRED_FOR_NEURAL_VOICE_QUALITY_GATE")
    normalized = path.with_name(f"{path.stem}.normalized.wav")
    command = [
        executable, "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
        # Reverse-trim-reverse preserves intentional pauses within the
        # performance while removing only leading and trailing silence.
        "-af", "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_duration=0.12:start_threshold=-50dB,areverse,loudnorm=I=-16:LRA=7:TP=-1.5",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(normalized),
    ]
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, shell=False)
    if process.returncode:
        normalized.unlink(missing_ok=True)
        raise NeuralVoiceError("NEURAL_VOICE_LOUDNESS_NORMALIZATION_FAILED")
    normalized.replace(path)
    return None


class AzureNeuralArabicVoiceProvider:
    """The single real, Azure REST-backed neural TTS adapter.

    The injected ``transport`` is solely for offline tests.  Live transport is
    reached only after all existing external-provider policy checks allow it.
    """

    provider_id = AZURE_NEURAL_PROVIDER
    model_id = "azure-speech-neural"

    def __init__(
        self,
        config: AzureNeuralVoiceConfig,
        credential_resolver: CredentialResolver,
        policy: ExternalAIExecutionPolicy,
        transport: Callable[[Request, float], bytes] | None = None,
    ) -> None:
        self.config = config
        self.credential_resolver = credential_resolver
        self.policy = policy
        self.transport = transport

    def _allow(self) -> str:
        for action in ("SEND_TO_EXTERNAL_PROVIDER", "USE_NETWORK", "ACCESS_SECRET"):
            decision = self.policy.decide(action, self.config.provider_id, self.model_id)
            if decision.decision != "ALLOW":
                raise NeuralVoiceError(f"POLICY_DENIED:{decision.rule_id}")
        secret = self.credential_resolver.resolve(self.config.subscription_key_reference)
        if not secret:
            raise NeuralVoiceError("AZURE_NEURAL_TTS_CREDENTIAL_UNAVAILABLE")
        return secret

    @staticmethod
    def _escape_xml(value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _request(self, item: NeuralVoiceRequest, secret: str) -> Request:
        text = normalize_arabic_for_tts(item.text, item.pronunciation_dictionary)
        if not text or any(token in text.lower() for token in _BANNED_NARRATION_METADATA):
            raise NeuralVoiceError("INVALID_NARRATION_TTS_TEXT")
        if item.hook_text and item.body_text:
            hook = normalize_arabic_for_tts(item.hook_text, item.pronunciation_dictionary)
            body = normalize_arabic_for_tts(item.body_text, item.pronunciation_dictionary)
            spoken = (
                f'<prosody rate="{self._escape_xml(item.speaking_rate)}" pitch="{self._escape_xml(item.pitch)}">'
                f'<emphasis level="{self._escape_xml(item.emphasis_level)}">{self._escape_xml(hook)}</emphasis>'
                f'<break time="{item.hook_break_ms}ms"/>'
                f'<prosody rate="{self._escape_xml(item.body_rate or item.speaking_rate)}">{self._escape_xml(body)}</prosody>'
                "</prosody>"
            )
        else:
            spoken = (
                f'<prosody rate="{self._escape_xml(item.speaking_rate)}" pitch="{self._escape_xml(item.pitch)}">'
                f'{self._escape_xml(text)}</prosody>'
            )
        ssml = (
            f'<speak version="1.0" xml:lang="{self._escape_xml(item.locale)}">'
            f'<voice name="{self._escape_xml(item.voice)}">{spoken}</voice></speak>'
        ).encode("utf-8")
        endpoint = self.config.endpoint.rstrip("/")
        # Azure resources commonly expose a generic cognitive-services URL;
        # Speech synthesis uses the regional TTS endpoint instead.
        if self.config.region and "tts.speech.microsoft.com" not in endpoint:
            endpoint = f"https://{self.config.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        if not endpoint.startswith("https://") or "speech.microsoft.com" not in endpoint:
            raise NeuralVoiceError("AZURE_NEURAL_TTS_INVALID_ENDPOINT")
        return Request(
            endpoint,
            data=ssml,
            headers={
                "Ocp-Apim-Subscription-Key": secret,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": self.config.output_format,
                "User-Agent": "siraj-quality-gate-v4",
            },
            method="POST",
        )

    @staticmethod
    def _normalize_error(error: BaseException) -> NeuralVoiceError:
        if isinstance(error, NeuralVoiceError):
            return error
        if isinstance(error, HTTPError):
            code = {400: "INVALID_REQUEST", 401: "AUTHENTICATION_FAILURE", 403: "PERMISSION_DENIED", 404: "ENDPOINT_UNAVAILABLE", 408: "TIMEOUT", 429: "RATE_LIMIT"}.get(error.code, "PROVIDER_SERVICE_FAILURE")
            return NeuralVoiceError(f"AZURE_NEURAL_TTS_{code}")
        if isinstance(error, TimeoutError):
            return NeuralVoiceError("AZURE_NEURAL_TTS_TIMEOUT")
        if isinstance(error, URLError):
            return NeuralVoiceError("AZURE_NEURAL_TTS_CONNECTION_FAILURE")
        return NeuralVoiceError("AZURE_NEURAL_TTS_PROVIDER_SERVICE_FAILURE")

    def synthesize(self, request: NeuralVoiceRequest) -> NeuralVoiceResult:
        secret = self._allow()
        target = Path(request.output_wav)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            response = self._request(request, secret)
            payload = self.transport(response, self.config.timeout_seconds) if self.transport else urlopen(response, timeout=self.config.timeout_seconds).read()  # nosec B310: explicit, policy-gated Azure endpoint
        except BaseException as error:
            raise self._normalize_error(error) from None
        if not payload:
            raise NeuralVoiceError("AZURE_NEURAL_TTS_EMPTY_RESPONSE")
        target.write_bytes(payload)
        try:
            duration = _duration_ms(target)
        except (NeuralVoiceError, wave.Error, EOFError) as error:
            target.unlink(missing_ok=True)
            raise NeuralVoiceError(str(error)) from error
        return NeuralVoiceResult(
            provider=self.provider_id,
            model=self.model_id,
            voice=request.voice,
            locale=request.locale,
            speaking_rate=request.speaking_rate,
            pitch=request.pitch,
            sample_rate_hz=request.sample_rate_hz,
            output_wav=str(target),
            duration_ms=duration,
            sha256=sha256(payload).hexdigest(),
            response_metadata={"transport": "AZURE_REST", "content_type": "audio/wav"},
        )


class AzureSpeechSDKArabicVoiceProvider(AzureNeuralArabicVoiceProvider):
    """Official Azure Speech SDK transport used after an empty REST response."""

    provider_id = "AZURE_NEURAL_TTS_SDK"
    model_id = "azure-speech-sdk-neural"

    @staticmethod
    def _safe_sdk_metadata(result: Any, speechsdk: Any) -> dict[str, str]:
        metadata = {
            "transport": "AZURE_SPEECH_SDK",
            "content_type": "audio/wav",
            "response_headers": "SDK_MANAGED_NOT_EXPOSED",
            "cancellation_reason": "NOT_CANCELED",
        }
        properties = getattr(result, "properties", None)
        request_property = getattr(getattr(speechsdk, "PropertyId", object), "SpeechServiceResponse_RequestId", None)
        if properties is not None and request_property is not None:
            request_id = properties.get_property(request_property)
            if request_id:
                metadata["request_id"] = str(request_id)
        return metadata

    def synthesize(self, request: NeuralVoiceRequest) -> NeuralVoiceResult:
        secret = self._allow()
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError as error:
            raise NeuralVoiceError("AZURE_SPEECH_SDK_NOT_INSTALLED") from error
        target = Path(request.output_wav)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            speech_config = speechsdk.SpeechConfig(subscription=secret, region=self.config.region or "")
            speech_config.speech_synthesis_voice_name = request.voice
            speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
            audio_config = speechsdk.audio.AudioOutputConfig(filename=str(target))
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
            ssml_request = self._request(request, secret)
            result = synthesizer.speak_ssml_async(ssml_request.data.decode("utf-8")).get()
            metadata = self._safe_sdk_metadata(result, speechsdk)
            if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
                cancellation = speechsdk.CancellationDetails.from_result(result)
                metadata["cancellation_reason"] = str(cancellation.reason)
                if cancellation.error_code:
                    metadata["cancellation_error_code"] = str(cancellation.error_code)
                target.unlink(missing_ok=True)
                raise NeuralVoiceError("AZURE_SPEECH_SDK_CANCELED")
            duration = _duration_ms(target)
        except NeuralVoiceError:
            raise
        except BaseException as error:
            target.unlink(missing_ok=True)
            raise self._normalize_error(error) from None
        return NeuralVoiceResult(
            provider=self.provider_id,
            model=self.model_id,
            voice=request.voice,
            locale=request.locale,
            speaking_rate=request.speaking_rate,
            pitch=request.pitch,
            sample_rate_hz=24_000,
            output_wav=str(target),
            duration_ms=duration,
            sha256=sha256(target.read_bytes()).hexdigest(),
            response_metadata=metadata,
        )


def run_azure_bassel_diagnostic(
    output_directory: str | Path,
    provider: NeuralVoiceProvider,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Run exactly one real-audio diagnostic before any three-voice audition."""

    output = Path(output_directory).expanduser().resolve(strict=False)
    report_path = output / "azure-diagnostic-report.json"
    if report_path.exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{report_path}")
    target = output / "azure-diagnostic.wav"
    try:
        result = provider.synthesize(NeuralVoiceRequest(
            _ARABIC_AUDITION_TEXT,
            str(target),
            "ar-IQ-BasselNeural",
            "ar-IQ",
            "-14%",
            "-1Hz",
        ))
        frames, rate, duration = validate_wav_audio(target)
        report = {
            "schema_version": VOICE_AUDITION_SCHEMA,
            "created_at": CANONICAL_TIMESTAMP,
            "status": "AUDIO_DIAGNOSTIC_PASS",
            "voice": result.voice,
            "duration_ms": duration,
            "frame_count": frames,
            "sample_rate_hz": rate,
            "sha256": sha256(target.read_bytes()).hexdigest(),
            "response_metadata": result.response_metadata,
        }
    except NeuralVoiceError as error:
        target.unlink(missing_ok=True)
        report = {
            "schema_version": VOICE_AUDITION_SCHEMA,
            "created_at": CANONICAL_TIMESTAMP,
            "status": "BLOCKED",
            "voice": "ar-IQ-BasselNeural",
            "reason": str(error),
            "response_metadata": {"transport": "AZURE_SPEECH_SDK"},
        }
    _atomic_write_json(report_path, report)
    return report


def run_azure_voice_audition_gate(
    output_directory: str | Path,
    provider: NeuralVoiceProvider,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Generate three Azure audition files, or emit a deterministic BLOCKED report.

    A blocked report never creates a fake audio substitute and deliberately
    prevents the caller from moving on to visual or final-render work.
    """

    output = Path(output_directory).expanduser().resolve(strict=False)
    report_path = output / "voice-audition-report.json"
    if report_path.exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{report_path}")
    provider_name = getattr(provider, "provider_id", "UNKNOWN").upper()
    if any(forbidden in provider_name for forbidden in _FORBIDDEN_PRODUCTION_PROVIDERS):
        raise NeuralVoiceError("PRODUCTION_REQUIRES_NEURAL_VOICE_PROVIDER")
    voices = (
        ("ar-SA-HamedNeural", "ar-SA", "+4%", "+2Hz", "moderate", 290, "+1%"),
        ("ar-EG-SalmaNeural", "ar-EG", "+6%", "+3Hz", "strong", 230, "+2%"),
        ("ar-IQ-BasselNeural", "ar-IQ", "+3%", "+1Hz", "moderate", 260, "+1%"),
    )
    samples: list[dict[str, Any]] = []
    try:
        for position, (voice, locale, rate, pitch, emphasis, hook_break_ms, body_rate) in enumerate(voices, 1):
            slug = re.sub(r"[^A-Za-z0-9]+", "-", voice).strip("-").lower()
            target = output / f"{position:02d}-{slug}-rate-{rate.replace('+', 'plus').replace('%', '')}-pitch-{pitch.replace('+', 'plus').replace('Hz', '')}.wav"
            if target.exists() and not replace:
                raise FileExistsError(f"ARTIFACT_EXISTS:{target}")
            request = NeuralVoiceRequest(
                _ARABIC_AUDITION_TEXT,
                str(target),
                voice,
                locale,
                rate,
                pitch,
                hook_text=_AUDITION_HOOK,
                body_text=_AUDITION_BODY,
                emphasis_level=emphasis,
                hook_break_ms=hook_break_ms,
                body_rate=body_rate,
            )
            result = provider.synthesize(request)
            _normalize_audition_wav(target)
            result = replace_dataclass(
                result,
                duration_ms=_duration_ms(target),
                sample_rate_hz=48_000,
                sha256=sha256(target.read_bytes()).hexdigest(),
            )
            if not 15_000 <= result.duration_ms <= 20_000:
                raise NeuralVoiceError(f"VOICE_AUDITION_DURATION_OUT_OF_RANGE:{result.duration_ms}")
            samples.append({
                "sample_id": deterministic_id("voice_audition_v4", [result.provider, result.voice, result.sha256]),
                "ssml_settings": {
                    "rate": rate,
                    "pitch": pitch,
                    "body_rate": body_rate,
                    "hook_emphasis": emphasis,
                    "hook_break_ms": hook_break_ms,
                },
                **asdict(result),
            })
    except NeuralVoiceError as error:
        for partial in output.glob("*-neural-rate-*-pitch-*.wav"):
            partial.unlink(missing_ok=True)
        report = {
            "schema_version": VOICE_AUDITION_SCHEMA,
            "created_at": CANONICAL_TIMESTAMP,
            "status": "BLOCKED",
            "gate": "NEURAL_ARABIC_VOICE_QUALIFICATION",
            "reason": str(error),
            "samples": [],
            "next_action": "Configure an approved Azure Neural TTS credential reference; no low-quality fallback is permitted.",
        }
        _atomic_write_json(report_path, report)
        return report
    report = {
        "schema_version": VOICE_AUDITION_SCHEMA,
        "created_at": CANONICAL_TIMESTAMP,
        "status": "READY_FOR_HUMAN_AUDITION",
        "gate": "NEURAL_ARABIC_VOICE_QUALIFICATION",
        "samples": samples,
        "narration_text": _ARABIC_AUDITION_TEXT,
        "comparison": [
            {
                "voice": sample["voice"],
                "clarity": "PENDING_HUMAN_LISTENING_REVIEW",
                "energy": f"SSML rate {sample['ssml_settings']['rate']}; emphasis {sample['ssml_settings']['hook_emphasis']}",
                "naturalness": "PENDING_HUMAN_LISTENING_REVIEW",
                "pacing": f"body rate {sample['ssml_settings']['body_rate']}; hook break {sample['ssml_settings']['hook_break_ms']}ms",
                "hook_strength": "FIRST_PHRASE_EMPHASIZED_WITH_INTENTIONAL_BREAK",
            }
            for sample in samples
        ],
    }
    _atomic_write_json(report_path, report)
    return report
