"""Offline, evidence-preserving research-to-approved-evidence episode adapter."""

from .runtime import (
    APPROVED_EVIDENCE_SCHEMA,
    RESEARCH_DOSSIER_SCHEMA,
    RESEARCH_VERIFICATION_SCHEMA,
    ResearchVerificationEpisodeAdapter,
    build_approved_evidence_runner,
    validate_source_package,
)

__all__ = [
    "APPROVED_EVIDENCE_SCHEMA", "RESEARCH_DOSSIER_SCHEMA", "RESEARCH_VERIFICATION_SCHEMA",
    "ResearchVerificationEpisodeAdapter", "build_approved_evidence_runner", "validate_source_package",
]
