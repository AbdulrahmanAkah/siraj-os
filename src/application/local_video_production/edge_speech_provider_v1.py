"""Unofficial Microsoft Edge speech provider for fallback use."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import tempfile

from .production_tts_v1 import (
    SegmentTTSProvider,
    TTSSegmentRequest,
    inspect_pcm_wav,
)


EDGE_SPEECH_PROVIDER_ID = (
    "edge-speech-v1"
)

EDGE_SPEECH_RETRYABLE_ERRORS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


class EdgeSpeechError(RuntimeError):
    pass


class EdgeSpeechRequestError(
    EdgeSpeechError
):
    pass


class EdgeSpeechTemporaryError(
    EdgeSpeechError
):
    pass


def _percentage(
    value: float,
) -> str:
    rounded = round(
        (value - 1.0) * 100
    )

    sign = "+" if rounded >= 0 else ""

    return f"{sign}{rounded}%"

def convert_edge_mp3_to_wav(
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
        raise EdgeSpeechRequestError(
            "EDGE_TTS_AUDIO_CONVERSION_FAILED:"
            + process.stderr[-2000:]
        )

    inspect_pcm_wav(
        target
    )

class EdgeSpeechProvider(
    SegmentTTSProvider
):
    provider_id = (
        EDGE_SPEECH_PROVIDER_ID
    )

    async def _synthesize_async(
        self,
        request: TTSSegmentRequest,
        output_path: Path,
    ) -> None:
        if not request.text.strip():
            raise EdgeSpeechRequestError(
                "EDGE_TTS_TEXT_REQUIRED"
            )

        if not request.voice_id.strip():
            raise EdgeSpeechRequestError(
                "EDGE_TTS_VOICE_REQUIRED"
            )

        if request.response_format != "wav":
            raise EdgeSpeechRequestError(
                "EDGE_TTS_OUTPUT_MUST_BE_WAV"
            )

        rate = _percentage(
            request.speed
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

            try:
                import edge_tts
            except ImportError as error:
                raise EdgeSpeechRequestError(
                    "EDGE_TTS_SDK_NOT_INSTALLED"
                ) from error

            communicator = edge_tts.Communicate(
                text=request.text,
                voice=request.voice_id,
                rate=rate,
            )

            try:
                await communicator.save(
                    str(mp3_path)
                )
            except Exception as error:
                raise EdgeSpeechTemporaryError(
                    "EDGE_TTS_SYNTHESIS_FAILED:"
                    f"{type(error).__name__}:"
                    f"{error}"
                ) from error

            convert_edge_mp3_to_wav(
                mp3_path,
                wav_path,
                sample_rate=(
                    request.sample_rate
                ),
            )

            wav_path.replace(
                output_path
            )

    def synthesize_segment(
        self,
        request: TTSSegmentRequest,
        output_path: Path,
    ) -> None:
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        asyncio.run(
            self._synthesize_async(
                request,
                output_path,
            )
        )
