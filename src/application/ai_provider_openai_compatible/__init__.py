"""The single real-provider adapter: OpenAI-compatible Responses HTTP API.

This adapter is not used by default tests.  It has no SDK dependency and its
only network path is guarded by an explicit external-execution policy.
"""

from .provider import (
    CredentialReference,
    CredentialResolver,
    ExternalAIExecutionPolicy,
    OpenAICompatibleProvider,
    OpenAICompatibleProviderConfig,
    RecordedProviderTransport,
)

__all__ = [
    "CredentialReference", "CredentialResolver", "ExternalAIExecutionPolicy",
    "OpenAICompatibleProvider", "OpenAICompatibleProviderConfig",
    "RecordedProviderTransport",
]
