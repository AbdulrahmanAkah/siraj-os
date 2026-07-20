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
from .pilot_evaluation import (
    ADJUDICATION_CATEGORIES,
    BLOCKED_ADJUDICATION_STATUS,
    PILOT_EVALUATION_SCHEMA_VERSION,
    POST_ADJUDICATION_STATUS,
    PRE_ADJUDICATION_STATUS,
    PilotEvaluationError,
    compare_pilot_12,
    evaluate_pilot_12,
    pilot_12_status,
    prepare_pilot_12_evaluation,
    run_real_model_pilot_12,
    select_evaluation_pilot_12,
)
from .pilot_workbench import (
    PilotAdjudicationError,
    PilotAdjudicationStore,
    build_pilot_workbench_server,
)
from .pilot_quick_review import (
    QUICK_COMPLETED,
    QUICK_JUDGMENTS,
    QUICK_PENDING,
    PilotQuickReviewStore,
    QuickReviewError,
    prepare_quick_review,
    quick_evaluate,
    quick_update,
)
from .critical_regression import (
    CRITICAL_SAMPLE,
    CriticalRegressionError,
    prepare_critical_4,
    run_critical_4,
)
from .gemini_cost import GEMINI_COST_SCHEMA_VERSION, estimate_gemini_cost
from .validation import canonicalize_literal_spans, validate_semantic_outputs


_GEMINI_EXPORTS = frozenset(
    {
        "GEMINI_PROVIDER_ID",
        "GeminiSemanticConfig",
        "GeminiSemanticProvider",
        "load_gemini_config",
        "probe_gemini_route",
        "prepare_gemini_critical_4",
        "run_gemini_critical_4",
        "run_gemini_schema_check",
    }
)


def __getattr__(name: str):
    if name in _GEMINI_EXPORTS:
        from importlib import import_module

        module = import_module(
            f"{__name__}.gemini_provider"
        )

        value = getattr(module, name)
        globals()[name] = value
        return value

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


def __dir__() -> list[str]:
    return sorted(
        set(globals()) | set(_GEMINI_EXPORTS)
    )

__all__ = [
    "DeterministicSemanticTestProvider",
    "FOUNDATION_VERSION",
    "LocalSemanticOrchestrator",
    "OllamaLocalSemanticConfig",
    "OllamaLocalSemanticProvider",
    "PILOT_SIZE",
    "PILOT_EVALUATION_SCHEMA_VERSION",
    "PRE_ADJUDICATION_STATUS",
    "POST_ADJUDICATION_STATUS",
    "BLOCKED_ADJUDICATION_STATUS",
    "ADJUDICATION_CATEGORIES",
    "PilotEvaluationError",
    "PilotAdjudicationError",
    "PilotAdjudicationStore",
    "SemanticExtractionProvider",
    "benchmark_pilot",
    "build_ollama_provider",
    "canonicalize_literal_spans",
    "compare_semantic_runs",
    "compare_pilot_12",
    "evaluate_pilot_12",
    "initialize_semantic_foundation",
    "load_provider_config",
    "run_semantic_segment",
    "run_real_model_pilot_12",
    "select_pilot_12",
    "semantic_status",
    "pilot_12_status",
    "prepare_pilot_12_evaluation",
    "select_evaluation_pilot_12",
    "build_pilot_workbench_server",
    "PilotQuickReviewStore",
    "QuickReviewError",
    "QUICK_COMPLETED",
    "QUICK_PENDING",
    "QUICK_JUDGMENTS",
    "prepare_quick_review",
    "quick_evaluate",
    "quick_update",
    "CRITICAL_SAMPLE",
    "CriticalRegressionError",
    "prepare_critical_4",
    "run_critical_4",
    "GEMINI_PROVIDER_ID",
    "GeminiSemanticConfig",
    "GeminiSemanticProvider",
    "load_gemini_config",
    "probe_gemini_route",
    "prepare_gemini_critical_4",
    "run_gemini_critical_4",
    "run_gemini_schema_check",
    "GEMINI_COST_SCHEMA_VERSION",
    "estimate_gemini_cost",
    "validate_semantic_outputs",
]
