"""Deterministic diagnostic voice provider for pipeline validation."""

from __future__ import annotations

from array import array
import math
from pathlib import Path
import wave
from typing import Any

from .voice_provider_v1 import (
    VOICE_REPORT_SCHEMA_V1,
    VoiceProvider,
    VoiceSynthesisResult,
    atomic_write_json,
    build_voice_segments,
    file_sha256,
    validate_voice_request,
)


DIAGNOSTIC_VOICE_PROVIDER_ID = (
    "siraj-diagnostic-tone-voice-v1"
)


def _resolve_output_path(
    project_root: Path,
    relative_path: str,
) -> Path:
    root = project_root.resolve()

    candidate = (
        root / relative_path
    ).resolve(strict=False)

    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "VOICE_OUTPUT_OUTSIDE_PROJECT"
        ) from error

    candidate.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return candidate


def _tone_samples(
    duration_ms: int,
    sample_rate: int,
    frequency_hz: float,
    amplitude: float,
) -> array:
    frame_count = max(
        1,
        round(
            duration_ms
            / 1000
            * sample_rate
        ),
    )

    samples = array("h")

    peak = int(
        32767
        * max(
            0.0,
            min(amplitude, 1.0),
        )
    )

    fade_frames = min(
        round(sample_rate * 0.02),
        max(1, frame_count // 4),
    )

    for frame in range(frame_count):
        envelope = 1.0

        if frame < fade_frames:
            envelope = frame / fade_frames
        elif frame >= frame_count - fade_frames:
            envelope = (
                frame_count - frame - 1
            ) / fade_frames

        value = (
            math.sin(
                2
                * math.pi
                * frequency_hz
                * frame
                / sample_rate
            )
            * peak
            * max(0.0, envelope)
        )

        samples.append(
            int(value)
        )

    return samples


def _silence_samples(
    duration_ms: int,
    sample_rate: int,
) -> array:
    frame_count = max(
        0,
        round(
            duration_ms
            / 1000
            * sample_rate
        ),
    )

    return array(
        "h",
        [0] * frame_count,
    )

def write_diagnostic_wav(
    output_path: Path,
    segment_durations_ms: list[int],
    *,
    sample_rate: int = 48_000,
    pause_ms: int = 180,
    amplitude: float = 0.18,
) -> int:
    if not segment_durations_ms:
        raise ValueError(
            "DIAGNOSTIC_SEGMENTS_REQUIRED"
        )

    if sample_rate not in {
        16_000,
        24_000,
        44_100,
        48_000,
    }:
        raise ValueError(
            "DIAGNOSTIC_SAMPLE_RATE_INVALID"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_samples = array("h")

    for index, duration_ms in enumerate(
        segment_durations_ms,
        start=1,
    ):
        if duration_ms <= 0:
            raise ValueError(
                "DIAGNOSTIC_DURATION_INVALID"
            )

        frequency_hz = (
            190.0
            + ((index - 1) % 5) * 35.0
        )

        all_samples.extend(
            _tone_samples(
                duration_ms=duration_ms,
                sample_rate=sample_rate,
                frequency_hz=frequency_hz,
                amplitude=amplitude,
            )
        )

        if index < len(
            segment_durations_ms
        ):
            all_samples.extend(
                _silence_samples(
                    duration_ms=pause_ms,
                    sample_rate=sample_rate,
                )
            )

    with wave.open(
        str(output_path),
        "wb",
    ) as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(
            sample_rate
        )
        handle.writeframes(
            all_samples.tobytes()
        )

    return round(
        len(all_samples)
        / sample_rate
        * 1000
    )

class DiagnosticToneVoiceProvider(
    VoiceProvider
):
    """Generate deterministic tones matching estimated narration timing."""

    provider_id = (
        DIAGNOSTIC_VOICE_PROVIDER_ID
    )

    def synthesize(
        self,
        request: dict[str, Any],
        project_root: Path,
    ) -> VoiceSynthesisResult:
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

        segments = build_voice_segments(
            request
        )

        output_config = request[
            "output"
        ]

        audio_path = _resolve_output_path(
            root,
            str(
                output_config["audio"]
            ),
        )

        report_path = _resolve_output_path(
            root,
            str(
                output_config["report"]
            ),
        )

        provider_config = request.get(
            "provider_config",
            {},
        )

        sample_rate = int(
            provider_config.get(
                "sample_rate",
                48_000,
            )
        )

        pause_ms = int(
            provider_config.get(
                "pause_ms",
                180,
            )
        )

        amplitude = float(
            provider_config.get(
                "amplitude",
                0.18,
            )
        )

        actual_duration_ms = (
            write_diagnostic_wav(
                output_path=audio_path,
                segment_durations_ms=[
                    segment.estimated_duration_ms
                    for segment in segments
                ],
                sample_rate=sample_rate,
                pause_ms=pause_ms,
                amplitude=amplitude,
            )
        )

        digest = file_sha256(
            audio_path
        )

        report = {
            "schema_version": (
                VOICE_REPORT_SCHEMA_V1
            ),
            "request_id": (
                request["request_id"]
            ),
            "episode_id": (
                request["episode_id"]
            ),
            "status": "VALID",
            "provider": self.provider_id,
            "production_voice": False,
            "diagnostic_only": True,
            "audio_path": str(
                audio_path
            ),
            "audio_sha256": digest,
            "sample_rate": sample_rate,
            "channels": 1,
            "sample_width_bytes": 2,
            "segment_count": len(
                segments
            ),
            "actual_duration_ms": (
                actual_duration_ms
            ),
            "segments": [
                {
                    "segment_id": (
                        segment.segment_id
                    ),
                    "order": (
                        segment.order
                    ),
                    "text": (
                        segment.text
                    ),
                    "normalized_text": (
                        segment.normalized_text
                    ),
                    "estimated_duration_ms": (
                        segment.estimated_duration_ms
                    ),
                }
                for segment in segments
            ],
        }

        atomic_write_json(
            report_path,
            report,
        )

        return VoiceSynthesisResult(
            status="VALID",
            provider=self.provider_id,
            output_path=str(
                audio_path
            ),
            report_path=str(
                report_path
            ),
            segment_count=len(
                segments
            ),
            output_sha256=digest,
        )