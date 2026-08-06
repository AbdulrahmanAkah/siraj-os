"""Optional local environment loading.

python-dotenv is a convenience dependency, not a requirement for offline CLI
execution or repository tests. When it is unavailable, environment variables
already supplied by the process remain unchanged.
"""

from __future__ import annotations

try:
    from dotenv import load_dotenv as _load_dotenv
except ModuleNotFoundError:
    def _load_dotenv(*args, **kwargs) -> bool:
        del args, kwargs
        return False


_load_dotenv()

__all__ = []
