"""OpenAI Speech API segment provider."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import (
    Request,
    urlopen,
)

from .production_tts_v1 import (
    SegmentTTSProvider,
    TTSSegmentRequest,
    inspect_pcm_wav,
)


OPENAI_SPEECH_PROVIDER_ID = (
    "openai-speech-v1"
)

DEFAULT_OPENAI_SPEECH_ENDPOINT = (
    "https://api.openai.com/v1/audio/speech"
)

OPENAI_SPEECH_MAX_INPUT_CHARACTERS = 4096


@dataclass(frozen=True)
class OpenAISpeechConfiguration:
    api_key_environment_variable: str = (
        "OPENAI_API_KEY"
    )
    endpoint: str = (
        DEFAULT_OPENAI_SPEECH_ENDPOINT
    )
    timeout_seconds: float = 90.0
    organization: str | None = None
    project: str | None = None


class OpenAISpeechError(RuntimeError):
    """Base error raised by the OpenAI speech provider."""


class OpenAISpeechAuthenticationError(
    OpenAISpeechError
):
    pass


class OpenAISpeechRateLimitError(
    OpenAISpeechError
):
    pass


class OpenAISpeechTemporaryError(
    OpenAISpeechError
):
    pass


class OpenAISpeechRequestError(
    OpenAISpeechError
):
    pass

def resolve_api_key(
    configuration: OpenAISpeechConfiguration,
) -> str:
    value = os.environ.get(
        configuration.api_key_environment_variable,
        "",
    ).strip()

    if not value:
        raise OpenAISpeechAuthenticationError(
            "OPENAI_API_KEY_MISSING"
        )

    return value


def validate_openai_segment_request(
    request: TTSSegmentRequest,
) -> None:
    if not request.text.strip():
        raise OpenAISpeechRequestError(
            "OPENAI_SPEECH_TEXT_REQUIRED"
        )

    if len(request.text) > (
        OPENAI_SPEECH_MAX_INPUT_CHARACTERS
    ):
        raise OpenAISpeechRequestError(
            "OPENAI_SPEECH_TEXT_TOO_LONG"
        )

    if not request.model.strip():
        raise OpenAISpeechRequestError(
            "OPENAI_SPEECH_MODEL_REQUIRED"
        )

    if not request.voice_id.strip():
        raise OpenAISpeechRequestError(
            "OPENAI_SPEECH_VOICE_REQUIRED"
        )

    if request.response_format != "wav":
        raise OpenAISpeechRequestError(
            "OPENAI_SPEECH_FORMAT_MUST_BE_WAV"
        )

    if (
        request.speed < 0.25
        or request.speed > 4.0
    ):
        raise OpenAISpeechRequestError(
            "OPENAI_SPEECH_SPEED_INVALID"
        )


def build_openai_speech_payload(
    request: TTSSegmentRequest,
) -> dict[str, Any]:
    validate_openai_segment_request(
        request
    )

    payload: dict[str, Any] = {
        "model": request.model,
        "input": request.text,
        "voice": request.voice_id,
        "response_format": "wav",
        "speed": request.speed,
    }

    if request.instructions:
        payload["instructions"] = (
            request.instructions
        )

    return payload


def build_openai_headers(
    api_key: str,
    configuration: OpenAISpeechConfiguration,
) -> dict[str, str]:
    headers = {
        "Authorization": (
            f"Bearer {api_key}"
        ),
        "Content-Type": "application/json",
        "Accept": "audio/wav",
        "User-Agent": "siraj-os/production-tts-v1",
    }

    if configuration.organization:
        headers["OpenAI-Organization"] = (
            configuration.organization
        )

    if configuration.project:
        headers["OpenAI-Project"] = (
            configuration.project
        )

    return headers

def _read_http_error_detail(
    error: HTTPError,
) -> str:
    try:
        content = error.read().decode(
            "utf-8",
            errors="replace",
        )
    except Exception:
        content = ""

    if not content:
        return str(error.reason)

    try:
        value = json.loads(content)

        if isinstance(value, dict):
            api_error = value.get(
                "error"
            )

            if isinstance(
                api_error,
                dict,
            ):
                message = api_error.get(
                    "message"
                )

                if isinstance(
                    message,
                    str,
                ):
                    return message
    except json.JSONDecodeError:
        pass

    return content[-2000:]


def classify_http_error(
    status_code: int,
    detail: str,
) -> OpenAISpeechError:
    message = (
        f"OPENAI_SPEECH_HTTP_{status_code}:"
        f"{detail}"
    )

    if status_code in {
        401,
        403,
    }:
        return (
            OpenAISpeechAuthenticationError(
                message
            )
        )

    if status_code == 429:
        return OpenAISpeechRateLimitError(
            message
        )

    if status_code in {
        408,
        409,
        500,
        502,
        503,
        504,
    }:
        return OpenAISpeechTemporaryError(
            message
        )

    return OpenAISpeechRequestError(
        message
    )


def validate_wav_response(
    content: bytes,
) -> None:
    if len(content) < 44:
        raise OpenAISpeechRequestError(
            "OPENAI_SPEECH_RESPONSE_TOO_SMALL"
        )

    if (
        content[:4] != b"RIFF"
        or content[8:12] != b"WAVE"
    ):
        raise OpenAISpeechRequestError(
            "OPENAI_SPEECH_RESPONSE_NOT_WAV"
        )

class OpenAISpeechProvider(
    SegmentTTSProvider
):
    """Generate one PCM WAV segment through OpenAI Speech."""

    provider_id = (
        OPENAI_SPEECH_PROVIDER_ID
    )

    def __init__(
        self,
        configuration: (
            OpenAISpeechConfiguration
            | None
        ) = None,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.configuration = (
            configuration
            or OpenAISpeechConfiguration()
        )
        self._opener = opener

    def synthesize_segment(
        self,
        request: TTSSegmentRequest,
        output_path: Path,
    ) -> None:
        api_key = resolve_api_key(
            self.configuration
        )

        payload = (
            build_openai_speech_payload(
                request
            )
        )

        encoded_payload = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        http_request = Request(
            url=self.configuration.endpoint,
            data=encoded_payload,
            headers=build_openai_headers(
                api_key,
                self.configuration,
            ),
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
            detail = _read_http_error_detail(
                error
            )

            raise classify_http_error(
                error.code,
                detail,
            ) from error

        except URLError as error:
            raise OpenAISpeechTemporaryError(
                "OPENAI_SPEECH_NETWORK_ERROR:"
                f"{error.reason}"
            ) from error

        except TimeoutError as error:
            raise OpenAISpeechTemporaryError(
                "OPENAI_SPEECH_TIMEOUT"
            ) from error

        validate_wav_response(
            content
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            suffix=".wav",
            delete=False,
        ) as handle:
            temporary = Path(
                handle.name
            )
            handle.write(content)

        try:
            inspect_pcm_wav(
                temporary
            )

            temporary.replace(
                output_path
            )
        finally:
            temporary.unlink(
                missing_ok=True
            )

OPENAI_SPEECH_RETRYABLE_ERRORS = (
    OpenAISpeechRateLimitError,
    OpenAISpeechTemporaryError,
)