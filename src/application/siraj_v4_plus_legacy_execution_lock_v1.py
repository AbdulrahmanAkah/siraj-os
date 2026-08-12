"""Lock legacy SIRAJ production execution surfaces after Episode 001 finalization."""
from __future__ import annotations

class LegacyExecutionLockedError(RuntimeError):
    pass

def block_legacy_execution(surface: str) -> None:
    raise LegacyExecutionLockedError(
        "LEGACY_EXECUTION_LOCKED_AFTER_EPISODE_001_FINAL:"
        + str(surface)
        + ":USE_SIRAJ_V4_PLUS_PIPELINE"
    )
