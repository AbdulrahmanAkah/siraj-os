"""Shared local-adapter security primitives.

The helpers intentionally reject ambiguous paths and never resolve a path
outside its supplied root.  They are independent of domain-layer models.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


SENSITIVE_KEYWORDS = ("secret", "password", "credential", "token", "api_key")


class SecurityBoundaryError(ValueError):
    """Raised when a local adapter request crosses an explicit boundary."""


def redact_sensitive(value: Any) -> Any:
    """Return a deterministic, recursively redacted representation."""
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {
            str(key): "REDACTED" if any(word in str(key).lower() for word in SENSITIVE_KEYWORDS)
            else redact_sensitive(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    return value


def contained_relative_path(root: str | Path, requested: str | Path) -> Path:
    """Validate a relative path, including alternate separators and symlinks."""
    raw = str(requested).replace("\\", "/")
    candidate = Path(raw)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise SecurityBoundaryError("PATH_TRAVERSAL_REJECTED")
    root_path = Path(root).resolve(strict=False)
    resolved = (root_path / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError as error:
        raise SecurityBoundaryError("OUTPUT_ROOT_ESCAPE_REJECTED") from error
    return resolved


def path_within_root(root: str | Path, candidate: str | Path) -> Path:
    """Validate an already-absolute path against a configured allowed root."""
    root_path = Path(root).resolve(strict=False)
    resolved = Path(candidate).resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError as error:
        raise SecurityBoundaryError("ALLOWED_ROOT_ESCAPE_REJECTED") from error
    return resolved
