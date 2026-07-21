from __future__ import annotations

from array import array
import json
from pathlib import Path
import wave

import pytest

from src.application.local_video_production.production_tts_v1 import (
    ProductionTTSOrchestrator,
    SegmentTTSProvider,
    TTSProviderRegistry,
    TTSRetryPolicy,
    TTSFallbackPolicy,
    TTSSegmentRequest,
    build_segment_cache_key,
    inspect_pcm_wav,
    run_with_retry,
)
from src.application.local_video_production.gemini_speech_provider_v1 import (
    GeminiTTSTimeoutError,
)
from src.application.local_video_production.voice_provider_v1 import (
    VOICE_REQUEST_SCHEMA_V1,
)


class FakeProvider(
    SegmentTTSProvider
):
    provider_id = "fake-provider-v1"

    def __init__(self) -> None:
        self.calls = 0

    def synthesize_segment(
        self,
        request: TTSSegmentRequest,
        output_path: Path,
    ) -> None:
        self.calls += 1
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        sample_rate = 48000
        samples = array(
            "h",
            [1000] * 4800,
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
                samples.tobytes()
            )


def sample_request() -> dict:
    return {
        "schema_version": (
            VOICE_REQUEST_SCHEMA_V1
        ),
        "request_id": "tts-test-001",
        "episode_id": "episode-test",
        "language": "ar",
        "text": (
            "هذه الجملة الأولى. "
            "وهذه الجملة الثانية."
        ),
        "voice": {
            "voice_id": "narrator",
            "speed": 1.0,
        },
        "segmentation": {
            "max_words": 12,
        },
        "tts": {
            "provider_id": (
                "fake-provider-v1"
            ),
            "model": "fake-model",
            "response_format": "wav",
            "sample_rate": 48000,
            "pause_ms": 100,
        },
        "output": {
            "audio": (
                "working/tts/final.wav"
            ),
            "report": (
                "manifests/tts-report.json"
            ),
        },
    }


def test_registry_registers_and_resolves() -> None:
    registry = TTSProviderRegistry()
    provider = FakeProvider()

    registry.register(provider)

    assert registry.resolve(
        provider.provider_id
    ) is provider


def test_registry_rejects_duplicate() -> None:
    registry = TTSProviderRegistry()
    provider = FakeProvider()

    registry.register(provider)

    with pytest.raises(
        ValueError,
        match="TTS_PROVIDER_ALREADY_REGISTERED",
    ):
        registry.register(provider)


def test_cache_key_is_deterministic() -> None:
    request = TTSSegmentRequest(
        segment_id="segment-001",
        text="نص عربي",
        language="ar",
        model="model",
        voice_id="voice",
        speed=1.0,
        instructions=None,
        response_format="wav",
        sample_rate=48000,
    )

    assert build_segment_cache_key(
        "provider",
        request,
    ) == build_segment_cache_key(
        "provider",
        request,
    )


def test_cache_key_changes_for_model_voice_and_style() -> None:
    base = TTSSegmentRequest("segment", "text", "ar", "model-a", "voice-a", 1.0, "style-a", "wav", 24000)
    key = build_segment_cache_key("gemini-tts-v1", base)
    assert key != build_segment_cache_key("gemini-tts-v1", TTSSegmentRequest("segment", "text", "ar", "model-b", "voice-a", 1.0, "style-a", "wav", 24000))
    assert key != build_segment_cache_key("gemini-tts-v1", TTSSegmentRequest("segment", "text", "ar", "model-a", "voice-b", 1.0, "style-a", "wav", 24000))
    assert key != build_segment_cache_key("gemini-tts-v1", TTSSegmentRequest("segment", "text", "ar", "model-a", "voice-a", 1.0, "style-b", "wav", 24000))


def test_retry_returns_successful_attempt() -> None:
    calls = {"count": 0}

    def operation() -> None:
        calls["count"] += 1

        if calls["count"] < 3:
            raise RuntimeError(
                "temporary"
            )

    attempts = run_with_retry(
        operation,
        TTSRetryPolicy(
            maximum_attempts=3,
            initial_delay_seconds=0,
        ),
    )

    assert attempts == 3


def test_orchestrator_reuses_cache(
    tmp_path: Path,
) -> None:
    registry = TTSProviderRegistry()
    provider = FakeProvider()

    registry.register(provider)

    orchestrator = (
        ProductionTTSOrchestrator(
            registry,
            retry_policy=TTSRetryPolicy(
                maximum_attempts=1,
            ),
        )
    )

    first = orchestrator.synthesize(
        sample_request(),
        tmp_path,
    )

    first_calls = provider.calls

    second = orchestrator.synthesize(
        sample_request(),
        tmp_path,
    )

    assert first.status == "VALID"
    assert second.status == "VALID"
    assert first.cache_misses == 2
    assert second.cache_hits == 2
    assert provider.calls == first_calls

    info = inspect_pcm_wav(
        Path(second.output_path)
    )

    assert info["channels"] == 1
    assert info["sample_rate"] == 48000

def test_retry_does_not_repeat_permanent_error() -> None:
    class PermanentError(RuntimeError):
        pass

    class TemporaryError(RuntimeError):
        pass

    calls = {"count": 0}

    def operation() -> None:
        calls["count"] += 1
        raise PermanentError(
            "permanent"
        )

    with pytest.raises(
        PermanentError,
        match="permanent",
    ):
        run_with_retry(
            operation,
            TTSRetryPolicy(
                maximum_attempts=3,
                initial_delay_seconds=0,
            ),
            retryable_exception=(
                TemporaryError
            ),
        )

    assert calls["count"] == 1


def test_gemini_primary_then_model_fallback_then_edge_after_retryable_failure(
    tmp_path: Path,
) -> None:
    class GeminiFailureProvider(FakeProvider):
        provider_id = "gemini-tts-v1"
        retryable_errors = (GeminiTTSTimeoutError,)

        def synthesize_segment(
            self,
            request: TTSSegmentRequest,
            output_path: Path,
        ) -> None:
            self.calls += 1
            raise GeminiTTSTimeoutError("temporary")

    class EmergencyProvider(FakeProvider):
        provider_id = "edge-speech-v1"

    request = sample_request()
    request["tts"]["provider_id"] = "gemini-tts-v1"
    request["tts"]["model"] = "gemini-3.1-flash-tts-preview"
    request["tts"]["sample_rate"] = 48000
    request["voice"]["voice_id"] = "Alnilam"
    primary = GeminiFailureProvider()
    emergency = EmergencyProvider()
    registry = TTSProviderRegistry()
    registry.register(primary)
    registry.register(emergency)

    result = ProductionTTSOrchestrator(
        registry,
        retry_policy=TTSRetryPolicy(maximum_attempts=2, initial_delay_seconds=0),
        fallback_policy=TTSFallbackPolicy(),
    ).synthesize(request, tmp_path)

    assert primary.calls == 8
    assert emergency.calls == 2
    report = json.loads((tmp_path / "manifests" / "tts-report.json").read_text(encoding="utf-8"))
    assert all(item["provider_id"] == "edge-speech-v1" for item in report["segments"])
    assert all(item["fallback_from_provider_id"] == "gemini-tts-v1" for item in report["segments"])


def test_gemini_model_fallback_succeeds_before_edge(
    tmp_path: Path,
) -> None:
    from src.application.local_video_production.gemini_speech_provider_v1 import GeminiTTSQuotaExhaustedError

    class ModelFallbackProvider(FakeProvider):
        provider_id = "gemini-tts-v1"
        retryable_errors: tuple[type[Exception], ...] = ()
        def synthesize_segment(self, request: TTSSegmentRequest, output_path: Path) -> None:
            self.calls += 1
            if request.model == "gemini-3.1-flash-tts-preview":
                raise GeminiTTSQuotaExhaustedError("quota")
            super().synthesize_segment(request, output_path)

    primary = ModelFallbackProvider(); edge = FakeProvider(); edge.provider_id = "edge-speech-v1"
    registry = TTSProviderRegistry(); registry.register(primary); registry.register(edge)
    request = sample_request(); request["tts"].update(provider_id="gemini-tts-v1", model="gemini-3.1-flash-tts-preview"); request["voice"]["voice_id"] = "Alnilam"
    result = ProductionTTSOrchestrator(registry, retry_policy=TTSRetryPolicy(maximum_attempts=1)).synthesize(request, tmp_path)
    assert result.status == "VALID"
    assert edge.calls == 0
    report = json.loads((tmp_path / "manifests" / "tts-report.json").read_text(encoding="utf-8"))
    assert all(item["model"] == "gemini-2.5-flash-preview-tts" for item in report["segments"])


def test_mastering_callback_is_cached_after_valid_result(tmp_path: Path) -> None:
    class Masterer:
        calls = 0
        def __call__(self, root: Path, source: str, output: str, report: str) -> object:
            self.calls += 1
            source_path, output_path, report_path = root / source, root / output, root / report
            output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_bytes(source_path.read_bytes())
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({"status": "VALID", "input_sha256": __import__("hashlib").sha256(source_path.read_bytes()).hexdigest(), "output_sha256": __import__("hashlib").sha256(output_path.read_bytes()).hexdigest()}), encoding="utf-8")
            return type("Result", (), {"status": "VALID"})()
    provider = FakeProvider(); registry = TTSProviderRegistry(); registry.register(provider); masterer = Masterer()
    request = sample_request(); request["tts"]["mastering"] = {"enabled": True, "output": "working/tts/mastered.wav", "report": "manifests/mastered.json"}
    orchestrator = ProductionTTSOrchestrator(registry, retry_policy=TTSRetryPolicy(maximum_attempts=1), masterer=masterer)
    assert orchestrator.synthesize(request, tmp_path).mastering_status == "VALID"
    assert orchestrator.synthesize(request, tmp_path).mastering_status == "CACHE_HIT"
    assert masterer.calls == 1
