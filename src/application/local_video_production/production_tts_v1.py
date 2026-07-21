"""Provider-independent production TTS orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any
import wave

from .voice_provider_v1 import (
    VoiceSegment,
    atomic_write_json,
    build_voice_segments,
    file_sha256,
    validate_voice_request,
)


PRODUCTION_TTS_REPORT_SCHEMA_V1 = (
    "siraj-production-tts-report-v1"
)

PRODUCTION_TTS_CACHE_SCHEMA_V1 = (
    "siraj-production-tts-cache-entry-v1"
)


@dataclass(frozen=True)
class TTSRetryPolicy:
    maximum_attempts: int = 3
    initial_delay_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    maximum_delay_seconds: float = 8.0


@dataclass(frozen=True)
class TTSSegmentRequest:
    segment_id: str
    text: str
    language: str
    model: str
    voice_id: str
    speed: float
    instructions: str | None
    response_format: str
    sample_rate: int


@dataclass(frozen=True)
class TTSSegmentResult:
    segment_id: str
    provider_id: str
    model: str
    output_path: str
    cache_key: str
    cache_hit: bool
    attempts: int
    sha256: str
    duration_ms: int
    fallback_from_provider_id: str | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True)
class ProductionTTSResult:
    status: str
    provider_id: str
    output_path: str
    report_path: str
    segment_count: int
    cache_hits: int
    cache_misses: int
    output_sha256: str
    mastering_status: str = "NOT_REQUESTED"


@dataclass(frozen=True)
class TTSRoute:
    provider_id: str
    model: str
    fallback_reason: str | None = None


@dataclass(frozen=True)
class TTSFallbackPolicy:
    """Gemini model fallback followed by Edge; paid/blocked providers never auto-run."""

    active_primary_provider_id: str = "gemini-tts-v1"
    active_primary_model: str = "gemini-3.1-flash-tts-preview"
    model_fallback: str = "gemini-2.5-flash-preview-tts"
    preferred_paid_provider_id: str = "elevenlabs-speech-v1"
    preferred_paid_status: str = "BLOCKED_BY_SUBSCRIPTION"
    emergency_provider_id: str = "edge-speech-v1"
    emergency_voice_id: str = "ar-KW-FahedNeural"
    google_cloud_status: str = "BLOCKED_BY_BILLING_COUNTRY"

    def route_chain(
        self,
        requested_provider_id: str,
        requested_model: str,
    ) -> tuple[TTSRoute, ...]:
        if requested_provider_id == self.active_primary_provider_id:
            primary_model = requested_model or self.active_primary_model
            return (
                TTSRoute(self.active_primary_provider_id, primary_model),
                TTSRoute(self.active_primary_provider_id, self.model_fallback, "GEMINI_PRIMARY_MODEL_FALLBACK"),
                TTSRoute(self.emergency_provider_id, primary_model, "GEMINI_TO_EDGE_EMERGENCY"),
            )
        return (TTSRoute(requested_provider_id, requested_model),)

    def request_for_provider(
        self,
        request: TTSSegmentRequest,
        route: TTSRoute,
    ) -> TTSSegmentRequest:
        if route.provider_id == self.emergency_provider_id:
            return replace(request, voice_id=self.emergency_voice_id, model=route.model)
        return replace(request, model=route.model)


class SegmentTTSProvider(ABC):
    """Provider contract for synthesizing one reviewed segment."""

    provider_id: str

    @abstractmethod
    def synthesize_segment(
        self,
        request: TTSSegmentRequest,
        output_path: Path,
    ) -> None:
        """Write one segment as mono PCM WAV."""

class TTSProviderRegistry:
    """Resolve replaceable TTS providers by stable provider ID."""

    def __init__(self) -> None:
        self._providers: dict[
            str,
            SegmentTTSProvider,
        ] = {}

    def register(
        self,
        provider: SegmentTTSProvider,
    ) -> None:
        provider_id = str(
            provider.provider_id
        ).strip()

        if not provider_id:
            raise ValueError(
                "TTS_PROVIDER_ID_REQUIRED"
            )

        if provider_id in self._providers:
            raise ValueError(
                f"TTS_PROVIDER_ALREADY_REGISTERED:{provider_id}"
            )

        self._providers[
            provider_id
        ] = provider

    def resolve(
        self,
        provider_id: str,
    ) -> SegmentTTSProvider:
        try:
            return self._providers[
                provider_id
            ]
        except KeyError as error:
            raise KeyError(
                f"TTS_PROVIDER_NOT_REGISTERED:{provider_id}"
            ) from error

    def provider_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                self._providers
            )
        )


def validate_retry_policy(
    policy: TTSRetryPolicy,
) -> None:
    if policy.maximum_attempts < 1:
        raise ValueError(
            "TTS_RETRY_ATTEMPTS_INVALID"
        )

    if policy.initial_delay_seconds < 0:
        raise ValueError(
            "TTS_RETRY_INITIAL_DELAY_INVALID"
        )

    if policy.backoff_multiplier < 1:
        raise ValueError(
            "TTS_RETRY_BACKOFF_INVALID"
        )

    if policy.maximum_delay_seconds < 0:
        raise ValueError(
            "TTS_RETRY_MAX_DELAY_INVALID"
        )


def run_with_retry(
    operation: Any,
    policy: TTSRetryPolicy,
    *,
    sleep_function: Any = time.sleep,
    retryable_exception: Any = Exception,
) -> int:
    validate_retry_policy(
        policy
    )

    delay = (
        policy.initial_delay_seconds
    )

    for attempt in range(
        1,
        policy.maximum_attempts + 1,
    ):
        try:
            operation()
            return attempt
        except Exception as error:
            if not isinstance(
                error,
                retryable_exception,
            ):
                raise

            if attempt >= (
                policy.maximum_attempts
            ):
                raise

            if delay > 0:
                sleep_function(
                    delay
                )

            delay = min(
                policy.maximum_delay_seconds,
                delay
                * policy.backoff_multiplier,
            )

    raise RuntimeError(
        "TTS_RETRY_STATE_INVALID"
    )

def build_segment_cache_key(
    provider_id: str,
    request: TTSSegmentRequest,
) -> str:
    payload = {
        "provider_id": provider_id,
        "segment_id": request.segment_id,
        "text": request.text,
        "language": request.language,
        "model": request.model,
        "voice_id": request.voice_id,
        "speed": request.speed,
        "instructions": (
            request.instructions
        ),
        "response_format": (
            request.response_format
        ),
        "sample_rate": (
            request.sample_rate
        ),
    }

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def resolve_cache_paths(
    cache_root: Path,
    cache_key: str,
) -> tuple[Path, Path]:
    prefix = cache_key[:2]

    directory = (
        cache_root
        / prefix
        / cache_key
    )

    return (
        directory / "segment.wav",
        directory / "entry.json",
    )


def read_valid_cache_entry(
    audio_path: Path,
    metadata_path: Path,
    expected_cache_key: str,
) -> dict[str, Any] | None:
    if (
        not audio_path.is_file()
        or not metadata_path.is_file()
    ):
        return None

    try:
        metadata = json.loads(
            metadata_path.read_text(
                encoding="utf-8-sig"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    if (
        metadata.get("schema_version")
        != PRODUCTION_TTS_CACHE_SCHEMA_V1
    ):
        return None

    if (
        metadata.get("cache_key")
        != expected_cache_key
    ):
        return None

    if (
        metadata.get("audio_sha256")
        != file_sha256(audio_path)
    ):
        return None

    return metadata


def write_cache_entry(
    audio_path: Path,
    metadata_path: Path,
    *,
    cache_key: str,
    provider_id: str,
    segment_id: str,
    duration_ms: int,
) -> None:
    atomic_write_json(
        metadata_path,
        {
            "schema_version": (
                PRODUCTION_TTS_CACHE_SCHEMA_V1
            ),
            "cache_key": cache_key,
            "provider_id": provider_id,
            "segment_id": segment_id,
            "audio_sha256": (
                file_sha256(audio_path)
            ),
            "duration_ms": (
                duration_ms
            ),
        },
    )


def _read_valid_mastering_cache(
    output_path: Path,
    report_path: Path,
    expected_input_sha256: str,
) -> bool:
    if not output_path.is_file() or not report_path.is_file():
        return False
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        report.get("status") == "VALID"
        and report.get("input_sha256") == expected_input_sha256
        and report.get("output_sha256") == file_sha256(output_path)
    )

def inspect_pcm_wav(
    path: Path,
) -> dict[str, int]:
    with wave.open(
        str(path),
        "rb",
    ) as handle:
        channels = (
            handle.getnchannels()
        )
        sample_width = (
            handle.getsampwidth()
        )
        sample_rate = (
            handle.getframerate()
        )
        frame_count = (
            handle.getnframes()
        )
        compression = (
            handle.getcomptype()
        )

    if compression != "NONE":
        raise ValueError(
            "TTS_WAV_MUST_BE_PCM"
        )

    if channels != 1:
        raise ValueError(
            "TTS_WAV_MUST_BE_MONO"
        )

    if sample_width != 2:
        raise ValueError(
            "TTS_WAV_SAMPLE_WIDTH_INVALID"
        )

    duration_ms = round(
        frame_count
        / sample_rate
        * 1000
    )

    return {
        "channels": channels,
        "sample_width": sample_width,
        "sample_rate": sample_rate,
        "frame_count": frame_count,
        "duration_ms": duration_ms,
    }


def concatenate_pcm_wav(
    input_paths: list[Path],
    output_path: Path,
    *,
    pause_ms: int = 160,
) -> int:
    if not input_paths:
        raise ValueError(
            "TTS_SEGMENT_AUDIO_REQUIRED"
        )

    first_info = inspect_pcm_wav(
        input_paths[0]
    )

    sample_rate = first_info[
        "sample_rate"
    ]

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_frames = 0

    with wave.open(
        str(output_path),
        "wb",
    ) as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(
            sample_rate
        )

        for index, input_path in enumerate(
            input_paths
        ):
            info = inspect_pcm_wav(
                input_path
            )

            if (
                info["sample_rate"]
                != sample_rate
            ):
                raise ValueError(
                    "TTS_SEGMENT_SAMPLE_RATE_MISMATCH"
                )

            with wave.open(
                str(input_path),
                "rb",
            ) as source:
                frames = source.readframes(
                    source.getnframes()
                )

            target.writeframes(
                frames
            )

            total_frames += (
                info["frame_count"]
            )

            if index < len(input_paths) - 1:
                silence_frames = round(
                    sample_rate
                    * pause_ms
                    / 1000
                )

                target.writeframes(
                    b"\x00\x00"
                    * silence_frames
                )

                total_frames += (
                    silence_frames
                )

    return round(
        total_frames
        / sample_rate
        * 1000
    )


def copy_atomic(
    source: Path,
    target: Path,
) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.NamedTemporaryFile(
        dir=target.parent,
        suffix=target.suffix,
        delete=False,
    ) as handle:
        temporary = Path(
            handle.name
        )

    try:
        shutil.copyfile(
            source,
            temporary,
        )
        temporary.replace(
            target
        )
    finally:
        temporary.unlink(
            missing_ok=True
        )

class ProductionTTSOrchestrator:
    """Synthesize, cache and concatenate reviewed narration segments."""

    def __init__(
        self,
        registry: TTSProviderRegistry,
        retry_policy: TTSRetryPolicy | None = None,
        retryable_exception: Any = Exception,
        fallback_policy: TTSFallbackPolicy | None = None,
        masterer: Any | None = None,
    ) -> None:
        self.registry = registry
        self.retry_policy = (
            retry_policy
            or TTSRetryPolicy()
        )
        self.retryable_exception = (
            retryable_exception
        )
        self.fallback_policy = fallback_policy or TTSFallbackPolicy()
        self.masterer = masterer

    def synthesize(
        self,
        request: dict[str, Any],
        project_root: str | Path,
    ) -> ProductionTTSResult:
        validate_voice_request(
            request
        )

        root = Path(
            project_root
        ).resolve()

        if not root.is_dir():
            raise FileNotFoundError(
                f"PROJECT_ROOT_NOT_FOUND:{root}"
            )

        tts_config = request.get(
            "tts",
            {},
        )

        provider_id = str(
            tts_config.get(
                "provider_id",
                "",
            )
        ).strip()

        if not provider_id:
            raise ValueError(
                "TTS_PROVIDER_ID_REQUIRED"
            )

        provider = (
            self.registry.resolve(
                provider_id
            )
        )

        model = str(
            tts_config.get(
                "model",
                "",
            )
        ).strip()

        if not model:
            raise ValueError(
                "TTS_MODEL_REQUIRED"
            )

        response_format = str(
            tts_config.get(
                "response_format",
                "wav",
            )
        ).lower()

        if response_format != "wav":
            raise ValueError(
                "TTS_RESPONSE_FORMAT_MUST_BE_WAV"
            )

        voice = request["voice"]
        segments = build_voice_segments(
            request
        )

        cache_root = (
            root
            / "cache"
            / "tts-v1"
        )

        output_config = request[
            "output"
        ]

        output_path = (
            root
            / str(
                output_config["audio"]
            )
        ).resolve(strict=False)

        report_path = (
            root
            / str(
                output_config["report"]
            )
        ).resolve(strict=False)

        for candidate in (
            output_path,
            report_path,
            cache_root,
        ):
            try:
                candidate.relative_to(
                    root
                )
            except ValueError as error:
                raise ValueError(
                    "TTS_PATH_OUTSIDE_PROJECT"
                ) from error

        segment_results: list[
            TTSSegmentResult
        ] = []

        segment_audio_paths: list[
            Path
        ] = []

        cache_hits = 0
        cache_misses = 0

        for segment in segments:
            segment_request = (
                TTSSegmentRequest(
                    segment_id=(
                        segment.segment_id
                    ),
                    text=(
                        segment.normalized_text
                    ),
                    language=str(
                        request["language"]
                    ),
                    model=model,
                    voice_id=str(
                        voice["voice_id"]
                    ),
                    speed=float(
                        voice.get(
                            "speed",
                            1.0,
                        )
                    ),
                    instructions=(
                        tts_config.get(
                            "instructions"
                        )
                    ),
                    response_format=(
                        response_format
                    ),
                    sample_rate=int(
                        tts_config.get(
                            "sample_rate",
                            48000,
                        )
                    ),
                )
            )

            attempts = 0
            fallback_from_provider_id: str | None = None
            fallback_reason: str | None = None
            last_error: Exception | None = None
            selected_provider: SegmentTTSProvider | None = None
            selected_request: TTSSegmentRequest | None = None
            cached_audio: Path | None = None
            cache_key = ""
            duration_ms = 0
            cache_hit = False

            for route in self.fallback_policy.route_chain(provider_id, model):
                candidate_provider_id = route.provider_id
                candidate_provider = self.registry.resolve(candidate_provider_id)
                candidate_request = self.fallback_policy.request_for_provider(
                    segment_request,
                    route,
                )
                candidate_cache_key = build_segment_cache_key(
                    candidate_provider.provider_id,
                    candidate_request,
                )
                candidate_audio, candidate_metadata = resolve_cache_paths(
                    cache_root,
                    candidate_cache_key,
                )
                cache_entry = read_valid_cache_entry(
                    candidate_audio,
                    candidate_metadata,
                    candidate_cache_key,
                )
                if cache_entry is not None:
                    cache_hits += 1
                    cache_hit = True
                    cached_audio = candidate_audio
                    cache_key = candidate_cache_key
                    duration_ms = int(cache_entry["duration_ms"])
                    selected_provider = candidate_provider
                    selected_request = candidate_request
                    break

                cache_misses += 1
                candidate_audio.parent.mkdir(parents=True, exist_ok=True)

                def operation() -> None:
                    candidate_provider.synthesize_segment(candidate_request, candidate_audio)
                    inspect_pcm_wav(candidate_audio)

                try:
                    attempts += run_with_retry(
                        operation,
                        self.retry_policy,
                        retryable_exception=getattr(
                            candidate_provider,
                            "retryable_errors",
                            self.retryable_exception,
                        ),
                    )
                    audio_info = inspect_pcm_wav(candidate_audio)
                    duration_ms = audio_info["duration_ms"]
                    write_cache_entry(
                        candidate_audio,
                        candidate_metadata,
                        cache_key=candidate_cache_key,
                        provider_id=candidate_provider.provider_id,
                        segment_id=segment.segment_id,
                        duration_ms=duration_ms,
                    )
                    cached_audio = candidate_audio
                    cache_key = candidate_cache_key
                    selected_provider = candidate_provider
                    selected_request = candidate_request
                    if (
                        candidate_provider_id != provider_id
                        or candidate_request.model != model
                    ):
                        fallback_from_provider_id = provider_id
                    break
                except Exception as error:
                    last_error = error
                    fallback_reason = type(error).__name__
                    if not getattr(error, "fallback_eligible", True):
                        raise

            if selected_provider is None or selected_request is None or cached_audio is None:
                assert last_error is not None
                raise last_error

            segment_audio_paths.append(
                cached_audio
            )

            segment_results.append(
                TTSSegmentResult(
                    segment_id=(
                        segment.segment_id
                    ),
                    provider_id=(selected_provider.provider_id),
                    model=selected_request.model,
                    output_path=str(
                        cached_audio
                    ),
                    cache_key=cache_key,
                    cache_hit=cache_hit,
                    attempts=attempts,
                    sha256=file_sha256(
                        cached_audio
                    ),
                    duration_ms=(
                        duration_ms
                    ),
                    fallback_from_provider_id=fallback_from_provider_id,
                    fallback_reason=fallback_reason if fallback_from_provider_id else None,
                )
            )

        pause_ms = int(
            tts_config.get(
                "pause_ms",
                160,
            )
        )

        final_duration_ms = (
            concatenate_pcm_wav(
                segment_audio_paths,
                output_path,
                pause_ms=pause_ms,
            )
        )

        mastering = tts_config.get("mastering", {})
        mastering_status = "NOT_REQUESTED"
        raw_output_path = output_path
        if mastering.get("enabled", False):
            mastered_relative = str(mastering.get("output", "")).strip()
            mastering_report_relative = str(mastering.get("report", "")).strip()
            if not mastered_relative or not mastering_report_relative:
                raise ValueError("TTS_MASTERING_OUTPUT_AND_REPORT_REQUIRED")
            mastered_path = (root / mastered_relative).resolve(strict=False)
            mastering_report_path = (root / mastering_report_relative).resolve(strict=False)
            for candidate in (mastered_path, mastering_report_path):
                try:
                    candidate.relative_to(root)
                except ValueError as error:
                    raise ValueError("TTS_PATH_OUTSIDE_PROJECT") from error
            raw_digest = file_sha256(raw_output_path)
            cached_mastering = _read_valid_mastering_cache(mastered_path, mastering_report_path, raw_digest)
            if cached_mastering:
                output_path = mastered_path
                mastering_status = "CACHE_HIT"
            else:
                if self.masterer is None:
                    from .audio_mastering_v1 import master_audio
                    masterer = master_audio
                else:
                    masterer = self.masterer
                result = masterer(root, str(raw_output_path.relative_to(root)), mastered_relative, mastering_report_relative)
                if getattr(result, "status", None) != "VALID":
                    raise RuntimeError("TTS_MASTERING_FAILED")
                output_path = mastered_path
                mastering_status = "VALID"

        digest = file_sha256(output_path)

        report = {
            "schema_version": (
                PRODUCTION_TTS_REPORT_SCHEMA_V1
            ),
            "status": "VALID",
            "provider_id": (
                provider.provider_id
            ),
            "provider_policy": {
                "active_primary_provider_id": self.fallback_policy.active_primary_provider_id,
                "active_primary_model": self.fallback_policy.active_primary_model,
                "model_fallback": self.fallback_policy.model_fallback,
                "preferred_paid_provider_id": self.fallback_policy.preferred_paid_provider_id,
                "preferred_paid_status": self.fallback_policy.preferred_paid_status,
                "emergency_provider_id": self.fallback_policy.emergency_provider_id,
                "google_cloud_status": self.fallback_policy.google_cloud_status,
            },
            "model": model,
            "episode_id": (
                request["episode_id"]
            ),
            "request_id": (
                request["request_id"]
            ),
            "output": str(
                output_path
            ),
            "raw_output": str(raw_output_path),
            "output_sha256": digest,
            "duration_ms": (
                final_duration_ms
            ),
            "segment_count": len(
                segment_results
            ),
            "cache_hits": (
                cache_hits
            ),
            "cache_misses": (
                cache_misses
            ),
            "mastering": {
                "status": mastering_status,
                "enabled": bool(mastering.get("enabled", False)),
            },
            "segments": [
                {
                    "segment_id": (
                        item.segment_id
                    ),
                    "provider_id": item.provider_id,
                    "model": item.model,
                    "cache_key": (
                        item.cache_key
                    ),
                    "cache_hit": (
                        item.cache_hit
                    ),
                    "attempts": (
                        item.attempts
                    ),
                    "duration_ms": (
                        item.duration_ms
                    ),
                    "sha256": (
                        item.sha256
                    ),
                    "audio": (
                        item.output_path
                    ),
                    "fallback_from_provider_id": item.fallback_from_provider_id,
                    "fallback_reason": item.fallback_reason,
                }
                for item in segment_results
            ],
        }

        atomic_write_json(
            report_path,
            report,
        )

        return ProductionTTSResult(
            status="VALID",
            provider_id=(
                provider.provider_id
            ),
            output_path=str(
                output_path
            ),
            report_path=str(
                report_path
            ),
            segment_count=len(
                segment_results
            ),
            cache_hits=cache_hits,
            cache_misses=(
                cache_misses
            ),
            output_sha256=digest,
            mastering_status=mastering_status,
        )

def build_production_tts_plan(
    request: dict[str, Any],
    project_root: str | Path,
    registry: TTSProviderRegistry,
) -> dict[str, Any]:
    validate_voice_request(
        request
    )

    root = Path(
        project_root
    ).resolve()

    if not root.is_dir():
        raise FileNotFoundError(
            f"PROJECT_ROOT_NOT_FOUND:{root}"
        )

    tts_config = request.get(
        "tts",
        {},
    )

    provider_id = str(
        tts_config.get(
            "provider_id",
            "",
        )
    ).strip()

    if not provider_id:
        raise ValueError(
            "TTS_PROVIDER_ID_REQUIRED"
        )

    provider = registry.resolve(
        provider_id
    )

    model = str(
        tts_config.get(
            "model",
            "",
        )
    ).strip()

    if not model:
        raise ValueError(
            "TTS_MODEL_REQUIRED"
        )

    response_format = str(
        tts_config.get(
            "response_format",
            "wav",
        )
    ).lower()

    if response_format != "wav":
        raise ValueError(
            "TTS_RESPONSE_FORMAT_MUST_BE_WAV"
        )

    voice = request["voice"]
    segments = build_voice_segments(
        request
    )

    cache_root = (
        root
        / "cache"
        / "tts-v1"
    )

    planned_segments: list[
        dict[str, Any]
    ] = []

    cache_hits = 0
    cache_misses = 0

    for segment in segments:
        segment_request = TTSSegmentRequest(
            segment_id=(
                segment.segment_id
            ),
            text=(
                segment.normalized_text
            ),
            language=str(
                request["language"]
            ),
            model=model,
            voice_id=str(
                voice["voice_id"]
            ),
            speed=float(
                voice.get(
                    "speed",
                    1.0,
                )
            ),
            instructions=(
                tts_config.get(
                    "instructions"
                )
            ),
            response_format=(
                response_format
            ),
            sample_rate=int(
                tts_config.get(
                    "sample_rate",
                    48000,
                )
            ),
        )

        cache_key = build_segment_cache_key(
            provider.provider_id,
            segment_request,
        )

        (
            audio_path,
            metadata_path,
        ) = resolve_cache_paths(
            cache_root,
            cache_key,
        )

        cache_entry = read_valid_cache_entry(
            audio_path,
            metadata_path,
            cache_key,
        )

        cache_hit = (
            cache_entry is not None
        )

        if cache_hit:
            cache_hits += 1
        else:
            cache_misses += 1

        planned_segments.append(
            {
                "segment_id": (
                    segment.segment_id
                ),
                "text": (
                    segment.normalized_text
                ),
                "character_count": len(
                    segment.normalized_text
                ),
                "estimated_duration_ms": (
                    segment.estimated_duration_ms
                ),
                "cache_key": cache_key,
                "cache_hit": cache_hit,
                "cache_audio": str(
                    audio_path
                ),
            }
        )

    return {
        "status": "VALID",
        "dry_run": True,
        "provider_id": (
            provider.provider_id
        ),
        "model": model,
        "voice_id": str(
            voice["voice_id"]
        ),
        "speed": float(
            voice.get(
                "speed",
                1.0,
            )
        ),
        "response_format": (
            response_format
        ),
        "sample_rate": int(
            tts_config.get(
                "sample_rate",
                48000,
            )
        ),
        "segment_count": len(
            planned_segments
        ),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "external_api_called": False,
        "segments": planned_segments,
    }
