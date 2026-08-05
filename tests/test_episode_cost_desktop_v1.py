from __future__ import annotations

from pathlib import Path


def test_desktop_cost_box_contract() -> None:
    source = Path(
        "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")

    required = (
        "episodeCostBreakdownBox",
        "episodeCostTotalLabel",
        "episodeCostDetailsTable",
        "current_episode_cost_breakdown",
        "تكلفة الحلقة الحالية",
        "الإجمالي المسجل",
        "المتبقي",
    )
    for marker in required:
        assert marker in source
