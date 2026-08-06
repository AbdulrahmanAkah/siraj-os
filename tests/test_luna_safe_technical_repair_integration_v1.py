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


def test_plan_includes_automatic_safe_repair_reserve() -> None:
    inspection = inspect_invalid_luna_retry(Path.cwd())
    if inspection.get("manual_review_required") is True:
        return
    plan = inspect_consolidated_production_plan(Path.cwd())
    expected = CONSOLIDATED_MAXIMUM_USD
    if inspection.get("retry_required") is True:
        expected += SUPPLEMENTAL_MAXIMUM_USD
    expected += SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD
    assert plan.maximum_authorized_usd == round(expected, 6)
    assert plan.maximum_authorized_usd < plan.episode_hard_cap_usd


def test_console_uses_auto_repair_wrapper() -> None:
    text = Path(
        "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    assert "run_consolidated_production_with_safe_technical_repair" in text
    assert "الإصلاح التقني المقيد: تلقائي" in text
