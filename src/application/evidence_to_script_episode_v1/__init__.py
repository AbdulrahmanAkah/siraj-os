"""Canonical evidence-to-script episode adapter contracts."""

from .runtime import (
    EvidenceToScriptEpisodeAdapter,
    EvidenceBoundScriptWriter,
    DEFAULT_NARRATIVE_MODEL_POLICY,
    build_narrative_stage_spec,
    validate_evidence_package,
    validate_episode_script,
    validate_model_policy,
)
from .gemini_writer import (
    GeminiEvidenceBoundScriptWriter,
    GeminiNarrativeWriterConfig,
    GoogleGenAINarrativeTransport,
)

__all__ = [
    "EvidenceToScriptEpisodeAdapter",
    "EvidenceBoundScriptWriter",
    "DEFAULT_NARRATIVE_MODEL_POLICY",
    "build_narrative_stage_spec",
    "validate_evidence_package",
    "validate_episode_script",
    "validate_model_policy",
    "GeminiEvidenceBoundScriptWriter",
    "GeminiNarrativeWriterConfig",
    "GoogleGenAINarrativeTransport",
]
