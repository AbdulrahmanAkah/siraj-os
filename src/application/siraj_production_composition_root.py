"""Only supported composition root for episode production.

Legacy stage implementations remain compatibility adapters.  UI/CLI callers
must enter here so transition-ledger migration, authorization and paid gateway
guards cannot be bypassed accidentally.
"""

from __future__ import annotations

from pathlib import Path

from src.application.siraj_autopilot_v6_6 import (
    EVENTS_REVIEW_STAGE,
    authorization_phrase_for,
    authorize_current_stage,
    full_episode_authorization_active,
    inspect_autopilot,
    master_auth_path,
    run_until_gate,
)

__all__ = [
    "EVENTS_REVIEW_STAGE",
    "authorization_phrase_for",
    "authorize_current_stage",
    "full_episode_authorization_active",
    "inspect_autopilot",
    "master_auth_path",
    "run_until_gate",
    "production_entrypoint_identity",
]


def production_entrypoint_identity(repo_root: Path) -> dict[str, str]:
    return {
        "composition_root": __name__,
        "repository": str(Path(repo_root).resolve()),
        "policy": "LEDGER_AUTHORIZATION_PAID_GATEWAY_REQUIRED",
    }
