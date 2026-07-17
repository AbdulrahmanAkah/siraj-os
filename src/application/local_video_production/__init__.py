"""Deterministic, local-only MP4 vertical-slice production helpers."""

from .runtime import (
    PRODUCTION_SLICE_SCHEMA_VERSION,
    build_render,
    build_storyboard,
    build_subtitles,
    initialize_production,
    verify_render,
)
from .documentary_v2 import (
    build_documentary_v2_render,
    build_documentary_v2_storyboard,
    build_documentary_v2_subtitles,
    initialize_documentary_v2,
    verify_documentary_v2_render,
)
from .documentary_v3 import (
    DocumentaryV3Config,
    build_documentary_v3_assets,
    build_documentary_v3_render,
    build_documentary_v3_subtitles,
    initialize_documentary_v3,
    verify_documentary_v3_render,
)
from .neural_voice import (
    AZURE_NEURAL_PROVIDER,
    AzureNeuralArabicVoiceProvider,
    AzureNeuralVoiceConfig,
    AzureSpeechSDKArabicVoiceProvider,
    NeuralVoiceError,
    NeuralVoiceRequest,
    NeuralVoiceResult,
    run_azure_voice_audition_gate,
    run_azure_bassel_diagnostic,
    validate_wav_audio,
)
from .quality_gate_v4 import (
    CuratedGeneratedVisualProvider,
    VisualAssetSpec,
    VoiceProviderSelection,
    VoiceProviderRegistry,
    build_visual_auditions,
    create_quality_gate_voice_selection,
)
from .quality_gate_render_v4 import build_quality_gate_v4
from .episode_preproduction_v4 import build_episode_01_preproduction

__all__ = [
    "PRODUCTION_SLICE_SCHEMA_VERSION",
    "build_render",
    "build_storyboard",
    "build_subtitles",
    "initialize_production",
    "verify_render",
    "build_documentary_v2_render",
    "build_documentary_v2_storyboard",
    "build_documentary_v2_subtitles",
    "initialize_documentary_v2",
    "verify_documentary_v2_render",
    "build_documentary_v3_assets",
    "DocumentaryV3Config",
    "build_documentary_v3_render",
    "build_documentary_v3_subtitles",
    "initialize_documentary_v3",
    "verify_documentary_v3_render",
    "AZURE_NEURAL_PROVIDER",
    "AzureNeuralArabicVoiceProvider",
    "AzureNeuralVoiceConfig",
    "AzureSpeechSDKArabicVoiceProvider",
    "NeuralVoiceError",
    "NeuralVoiceRequest",
    "NeuralVoiceResult",
    "run_azure_voice_audition_gate",
    "run_azure_bassel_diagnostic",
    "validate_wav_audio",
    "CuratedGeneratedVisualProvider",
    "VisualAssetSpec",
    "VoiceProviderSelection",
    "VoiceProviderRegistry",
    "build_visual_auditions",
    "create_quality_gate_voice_selection",
    "build_quality_gate_v4",
    "build_episode_01_preproduction",
]
