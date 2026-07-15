"""Central credential resolution; adapters never read process environment."""

from __future__ import annotations

import os

from src.application.ai_provider_openai_compatible import CredentialReference


class EnvironmentCredentialResolver:
    """Resolve only explicitly named references without logging their values."""

    def __init__(self, allowed_references: set[str] | None = None):
        self.allowed_references = allowed_references or set()

    def resolve(self, reference: CredentialReference) -> str | None:
        if reference.reference not in self.allowed_references:
            return None
        return os.environ.get(reference.reference)
