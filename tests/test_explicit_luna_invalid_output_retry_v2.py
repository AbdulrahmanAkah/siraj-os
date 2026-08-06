from dataclasses import replace
from pathlib import Path

from src.application.consolidated_episode_production_controller_v2 import (
    CONSOLIDATED_MAXIMUM_USD,
    inspect_consolidated_production_plan,
)
from src.application.luna_invalid_output_recovery_v2 import (
    SUPPLEMENTAL_MAXIMUM_USD,
    inspect_invalid_luna_retry,
)
from src.application.luna_safe_technical_repair_v1 import (
    SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD,
)


def test_live_invalid_lock_requires_explicit_retry() -> None:
    inspection = inspect_invalid_luna_retry(Path.cwd())
    assert inspection["status"] in {
        "EXPLICIT_SUPPLEMENTAL_AUTHORIZATION_REQUIRED",
        "NO_EXPLICIT_LUNA_RETRY_REQUIRED",
        (
            "EXPLICIT_LUNA_RETRY_ALREADY_CONSUMED_"
            "MANUAL_REVIEW_REQUIRED"
        ),
    }


def test_controller_maximum_matches_retry_state() -> None:
    inspection = inspect_invalid_luna_retry(Path.cwd())
    if inspection.get("manual_review_required") is True:
        return
    plan = inspect_consolidated_production_plan(Path.cwd())
    if inspection.get("retry_required") is True:
        assert plan.maximum_authorized_usd == round(
            CONSOLIDATED_MAXIMUM_USD
            + SUPPLEMENTAL_MAXIMUM_USD
            + SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD,
            6,
        )
        assert "RETRY" in plan.status
    else:
        assert plan.maximum_authorized_usd == (
            CONSOLIDATED_MAXIMUM_USD
            + SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD
        )


def test_retry_is_never_automatic() -> None:
    module = Path(
        "src/application/luna_invalid_output_recovery_v2.py"
    ).read_text(encoding="utf-8")
    assert "CONSUMED_BEFORE_NETWORK" in module
    assert "EXPLICIT_DESKTOP_CONFIRMATION" in module
    assert 'automatic_retry": "FORBIDDEN"' in module
    assert "maximum_provider_requests" in module
