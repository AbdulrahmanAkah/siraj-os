"""Public boundary for Siraj local semantic intelligence foundation."""

from .foundation import (
    FOUNDATION_VERSION,
    PILOT_SIZE,
    benchmark_pilot,
    build_ollama_provider,
    compare_semantic_runs,
    initialize_semantic_foundation,
    load_provider_config,
    run_semantic_segment,
    select_pilot_12,
    semantic_status,
)
from .models import *
from .ollama_provider import (
    OllamaLocalSemanticConfig,
    OllamaLocalSemanticProvider,
)
from .orchestrator import LocalSemanticOrchestrator
from .provider import (
    DeterministicSemanticTestProvider,
    SemanticExtractionProvider,
)
from .validation import canonicalize_literal_spans, validate_semantic_outputs

__all__ = [
    "DeterministicSemanticTestProvider",
    "FOUNDATION_VERSION",
    "LocalSemanticOrchestrator",
    "OllamaLocalSemanticConfig",
    "OllamaLocalSemanticProvider",
    "PILOT_SIZE",
    "SemanticExtractionProvider",
    "benchmark_pilot",
    "build_ollama_provider",
    "canonicalize_literal_spans",
    "compare_semantic_runs",
    "initialize_semantic_foundation",
    "load_provider_config",
    "run_semantic_segment",
    "select_pilot_12",
    "semantic_status",
    "validate_semantic_outputs",
]
