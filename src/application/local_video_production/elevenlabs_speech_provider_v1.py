"""ElevenLabs multilingual speech provider."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .production_tts_v1 import (
    SegmentTTSProvider,
    TTSSegmentRequest,
    inspect_pcm_wav,
)


ELEVENLABS_SPEECH_PROVIDER_ID = (
    "elevenlabs-speech-v1"
)

DEFAULT_ELEVENLABS_ENDPOINT = (
    "https://api.elevenlabs.io/v1/"
    "text-to-speech"
)


@dataclass(frozen=True)
class ElevenLabsSpeechConfiguration:
    api_key_environment_variable: str = (
        "ELEVENLABS_API_KEY"
    )
    endpoint: str = (
        DEFAULT_ELEVENLABS_ENDPOINT
    )
    timeout_seconds: float = 90.0
    output_format: str = (
        "mp3_44100_128"
    )


class ElevenLabsSpeechError(RuntimeError):
    pass


class ElevenLabsAuthenticationError(
    ElevenLabsSpeechError
):
    pass


class ElevenLabsRateLimitError(
    ElevenLabsSpeechError
):
    pass


class ElevenLabsSubscriptionBlockedError(
    ElevenLabsSpeechError
):
    """The configured Voice Library voice needs a paid subscription."""
    pass


class ElevenLabsTemporaryError(
    ElevenLabsSpeechError
):
    pass


class ElevenLabsRequestError(
    ElevenLabsSpeechError
):
    pass


ELEVENLABS_RETRYABLE_ERRORS = (
    ElevenLabsRateLimitError,
    ElevenLabsTemporaryError,
)

def resolve_elevenlabs_api_key(
    configuration: ElevenLabsSpeechConfiguration,
) -> str:
    value = os.environ.get(
        configuration.api_key_environment_variable,
        "",
    ).strip()

    if not value:
        raise ElevenLabsAuthenticationError(
            "ELEVENLABS_API_KEY_MISSING"
        )

    return value


def validate_elevenlabs_request(
    request: TTSSegmentRequest,
) -> None:
    if not request.text.strip():
        raise ElevenLabsRequestError(
            "ELEVENLABS_TEXT_REQUIRED"
        )

    if not request.voice_id.strip():
        raise ElevenLabsRequestError(
            "ELEVENLABS_VOICE_ID_REQUIRED"
        )

    if not request.model.strip():
        raise ElevenLabsRequestError(
            "ELEVENLABS_MODEL_REQUIRED"
        )

    if request.response_format != "wav":
        raise ElevenLabsRequestError(
            "SIRAJ_OUTPUT_FORMAT_MUST_BE_WAV"
        )


def build_elevenlabs_payload(
    request: TTSSegmentRequest,
) -> dict[str, Any]:
    validate_elevenlabs_request(
        request
    )

    return {
        "text": request.text,
        "model_id": request.model,
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.75,
            "style": 0.15,
            "use_speaker_boost": True,
        },
    }


def classify_elevenlabs_http_error(
    status_code: int,
    detail: str,
) -> ElevenLabsSpeechError:
    message = (
        f"ELEVENLABS_HTTP_{status_code}:"
        f"{detail}"
    )

    if status_code in {
        401,
        403,
    }:
        return ElevenLabsAuthenticationError(
            message
        )

    if status_code == 429:
        return ElevenLabsRateLimitError(
            message
        )

    if status_code == 402:
        return ElevenLabsSubscriptionBlockedError(
            "ELEVENLABS_BLOCKED_BY_SUBSCRIPTION"
        )

    if status_code in {
        408,
        409,
        500,
        502,
        503,
        504,
    }:
        return ElevenLabsTemporaryError(
            message
        )

    return ElevenLabsRequestError(
        message
    )


def read_http_error_detail(
    error: HTTPError,
) -> str:
    try:
        content = error.read().decode(
            "utf-8",
            errors="replace",
        )
    except Exception:
        return str(error.reason)

    try:
        value = json.loads(content)

        detail = value.get(
            "detail"
        )

        if isinstance(detail, dict):
            message = detail.get(
                "message"
            )

            if isinstance(message, str):
                return message

        if isinstance(detail, str):
            return detail
    except json.JSONDecodeError:
        pass

    return content[-2000:]

def convert_mp3_to_pcm_wav(
    source: Path,
    target: Path,
    *,
    sample_rate: int,
) -> None:
    process = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )

    if process.returncode != 0:
        raise ElevenLabsRequestError(
            "ELEVENLABS_AUDIO_CONVERSION_FAILED:"
            + process.stderr[-2000:]
        )

    inspect_pcm_wav(
        target
    )

class ElevenLabsSpeechProvider(
    SegmentTTSProvider
):
    provider_id = (
        ELEVENLABS_SPEECH_PROVIDER_ID
    )

    def __init__(
        self,
        configuration: (
            ElevenLabsSpeechConfiguration
            | None
        ) = None,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.configuration = (
            configuration
            or ElevenLabsSpeechConfiguration()
        )
        self._opener = opener

    def synthesize_segment(
        self,
        request: TTSSegmentRequest,
        output_path: Path,
    ) -> None:
        api_key = (
            resolve_elevenlabs_api_key(
                self.configuration
            )
        )

        payload = json.dumps(
            build_elevenlabs_payload(
                request
            ),
            ensure_ascii=False,
        ).encode("utf-8")

        voice_id = quote(
            request.voice_id,
            safe="",
        )

        endpoint = (
            self.configuration.endpoint.rstrip("/")
            + "/"
            + voice_id
            + "?output_format="
            + quote(
                self.configuration.output_format,
                safe="",
            )
        )

        http_request = Request(
            url=endpoint,
            data=payload,
            headers={
                "xi-api-key": api_key,
                "Content-Type": (
                    "application/json"
                ),
                "Accept": "audio/mpeg",
                "User-Agent": (
                    "siraj-os/production-tts-v1"
                ),
            },
            method="POST",
        )

        try:
            response = self._opener(
                http_request,
                timeout=(
                    self.configuration
                    .timeout_seconds
                ),
            )

            with response:
                content = response.read()

        except HTTPError as error:
            raise classify_elevenlabs_http_error(
                error.code,
                read_http_error_detail(
                    error
                ),
            ) from error

        except URLError as error:
            raise ElevenLabsTemporaryError(
                "ELEVENLABS_NETWORK_ERROR:"
                f"{error.reason}"
            ) from error

        except TimeoutError as error:
            raise ElevenLabsTemporaryError(
                "ELEVENLABS_TIMEOUT"
            ) from error

        if len(content) < 100:
            raise ElevenLabsRequestError(
                "ELEVENLABS_RESPONSE_TOO_SMALL"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with tempfile.TemporaryDirectory(
            dir=output_path.parent
        ) as temporary_directory:
            temporary_root = Path(
                temporary_directory
            )

            mp3_path = (
                temporary_root
                / "response.mp3"
            )

            wav_path = (
                temporary_root
                / "response.wav"
            )

            mp3_path.write_bytes(
                content
            )

            convert_mp3_to_pcm_wav(
                mp3_path,
                wav_path,
                sample_rate=(
                    request.sample_rate
                ),
            )

            wav_path.replace(
                output_path
            )
