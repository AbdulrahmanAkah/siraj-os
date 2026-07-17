"""Read-only local discovery helpers for an installed Shamela library.

This package deliberately stops before source-adapter construction or book
import.  It inventories local storage, inspects SQLite schemas in immutable
mode, and writes bounded discovery reports to an explicit external location.
"""

from .discovery import (
    DISCOVERY_SCHEMA_VERSION,
    DiscoverySafetyError,
    build_locator,
    classify_storage,
    discover_candidates,
    generate_discovery_reports,
    sanitize_public_path,
)

__all__ = [
    "DISCOVERY_SCHEMA_VERSION",
    "DiscoverySafetyError",
    "build_locator",
    "classify_storage",
    "discover_candidates",
    "generate_discovery_reports",
    "sanitize_public_path",
]
