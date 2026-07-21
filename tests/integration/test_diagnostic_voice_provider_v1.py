from __future__ import annotations

import json
from pathlib import Path
import wave

from src.application.local_video_production.diagnostic_voice_provider_v1 import (
    DIAGNOSTIC_VOICE_PROVIDER_ID,
    DiagnosticToneVoiceProvider,
    write_diagnostic_wav,
)
from src.application.local_video_production.voice_provider_v1 import (
    VOICE_REQUEST_SCHEMA_V1,
)


def sample_request() -> dict:
    return {
        "schema_version": (
            VOICE_REQUEST_SCHEMA_V1
        ),
        "request_id": (
            "diagnostic-voice-test"
        ),
        "episode_id": "episode-test",
        "language": "ar",
        "text": (
            "بدأت القصة منذ زمن بعيد. "
            "ثم انتقل الناس إلى أرض أخرى."
        ),
        "voice": {
            "voice_id": (
                "diagnostic-tone"
            ),
            "speed": 1.0,
        },
        "segmentation": {
            "max_words": 12,
        },
        "provider_config": {
            "sample_rate": 48000,
            "pause_ms": 150,
            "amplitude": 0.12,
        },
        "output": {
            "audio": (
                "audio/diagnostic.wav"
            ),
            "report": (
                "reports/diagnostic.json"
            ),
        },
    }


def test_write_diagnostic_wav_creates_pcm_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "tone.wav"

    duration_ms = write_diagnostic_wav(
        target,
        [700, 900],
        sample_rate=48000,
        pause_ms=100,
    )

    assert target.is_file()
    assert duration_ms == 1700

    with wave.open(
        str(target),
        "rb",
    ) as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 48000


def test_provider_creates_audio_and_report(
    tmp_path: Path,
) -> None:
    provider = (
        DiagnosticToneVoiceProvider()
    )

    result = provider.synthesize(
        sample_request(),
        tmp_path,
    )

    assert result.status == "VALID"
    assert result.provider == (
        DIAGNOSTIC_VOICE_PROVIDER_ID
    )
    assert result.segment_count == 2

    audio_path = Path(
        result.output_path
    )

    report_path = Path(
        result.report_path
    )

    assert audio_path.is_file()
    assert report_path.is_file()

    report = json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )

    assert report["status"] == "VALID"
    assert report["diagnostic_only"] is True
    assert report["production_voice"] is False
    assert report["segment_count"] == 2
    assert report["audio_sha256"] == (
        result.output_sha256
    )