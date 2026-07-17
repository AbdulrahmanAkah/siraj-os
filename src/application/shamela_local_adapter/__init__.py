"""Read-only local Shamela source adapter and bounded pilot-corpus workflow."""

from .adapter import (
    ADAPTER_VERSION,
    LuceneUnavailableError,
    ShamelaLocalSourceAdapter,
    conservative_normalize,
)
from .pilot import PILOT_BOOKS, build_pilot_corpus

__all__ = [
    "ADAPTER_VERSION",
    "LuceneUnavailableError",
    "PILOT_BOOKS",
    "ShamelaLocalSourceAdapter",
    "build_pilot_corpus",
    "conservative_normalize",
]
