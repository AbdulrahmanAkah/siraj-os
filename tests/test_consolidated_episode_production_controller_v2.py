from __future__ import annotations

from pathlib import Path

from src.application.consolidated_episode_production_controller_v2 import (
    CONSOLIDATED_MAXIMUM_USD,
    GENERATED_VIDEO_PLANNED_USD,
    OTHER_MEDIA_RESERVE_USD,
    PROMPT_DIRECTION_RESERVE_USD,
    TOTAL_EPISODE_HARD_CAP_USD,
    TTS_RESERVE_USD,
    inspect_consolidated_production_plan,
)


def test_consolidated_budget_is_exact_and_below_hard_cap() -> None:
    assert GENERATED_VIDEO_PLANNED_USD == 29.514375
    assert PROMPT_DIRECTION_RESERVE_USD == 0.35
    assert TTS_RESERVE_USD == 3.0
    assert OTHER_MEDIA_RESERVE_USD == 2.0
    assert CONSOLIDATED_MAXIMUM_USD == 34.864375
    assert CONSOLIDATED_MAXIMUM_USD < TOTAL_EPISODE_HARD_CAP_USD


def test_real_repository_plan_is_ready() -> None:
    plan = inspect_consolidated_production_plan(Path.cwd())
    assert plan.blocking_issue_count == 0
    assert plan.prompt_item_count == 70
    assert plan.prompt_batch_count == 7
    assert plan.tts_block_count == 43
    assert plan.full_episode_production_authorized is False
    assert plan.maximum_authorized_usd in {
        34.864375,
        34.914375,
    }
    if "RETRY" in plan.status:
        assert plan.maximum_authorized_usd == 34.914375
    else:
        assert plan.maximum_authorized_usd == 34.864375


def test_runtime_requires_all_provider_keys_and_forbids_hidden_retry() -> None:
    module = Path(
        "src/application/consolidated_episode_production_controller_v2.py"
    ).read_text(encoding="utf-8")
    assert "OPENAI_API_KEY_REQUIRED_FOR_LUNA_PROMPT_DIRECTION" in module
    assert "RUNWARE_API_KEY_REQUIRED" in module
    assert "ELEVENLABS_API_KEY_REQUIRED" in module
    assert 'automatic_paid_retry="FORBIDDEN"' in module


def test_ui_contains_one_consolidated_authorization_button() -> None:
    ui = Path(
        "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    assert "consolidatedEpisodeProductionV2Button" in ui
    assert "تفويض موحد وبدء إنتاج الحلقة كاملة" in ui
    assert "ConsolidatedEpisodeProductionThread" in ui
