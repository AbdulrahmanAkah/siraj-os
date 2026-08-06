from pathlib import Path

from src.application.consolidated_episode_production_controller_v2 import (
    TOTAL_EPISODE_HARD_CAP_USD,
    inspect_consolidated_production_plan,
)
from src.application.production_standard_v2_native_assets import (
    inspect_native_execution_plan,
)


def test_native_consolidated_budget_is_exact_and_below_hard_cap() -> None:
    native = inspect_native_execution_plan(Path.cwd())
    plan = inspect_consolidated_production_plan(Path.cwd())
    assert plan.maximum_authorized_usd == (
        native["consolidated_maximum_usd"]
    )
    assert plan.maximum_authorized_usd < (
        TOTAL_EPISODE_HARD_CAP_USD
    )
    assert plan.generated_video_planned_usd == (
        native["generated_video_maximum_usd"]
    )
    assert plan.other_media_reserve_usd == (
        native["image_maximum_usd"]
    )


def test_real_repository_plan_is_ready() -> None:
    plan = inspect_consolidated_production_plan(Path.cwd())
    assert plan.blocking_issue_count == 0
    assert plan.prompt_item_count == 70
    assert plan.certified_prompt_count == 70
    assert plan.prompt_batch_count == 7
    assert plan.pending_prompt_batch_count == 0
    assert plan.tts_block_count == 43
    assert plan.full_episode_production_authorized is False
    assert plan.status == (
        "READY_FOR_CONSOLIDATED_V2_EXECUTION_AUTHORIZATION"
    )


def test_runtime_requires_provider_keys_and_forbids_hidden_retry() -> None:
    module = Path(
        "src/application/consolidated_episode_production_controller_v2.py"
    ).read_text(encoding="utf-8")
    assert "OPENAI_API_KEY_REQUIRED_FOR_SAFE_TECHNICAL_REPAIR" in module
    assert "RUNWARE_API_KEY_REQUIRED" in module
    assert "ELEVENLABS_API_KEY_REQUIRED" in module
    assert "automatic_paid_retry" in module
    assert "FORBIDDEN" in module


def test_ui_contains_one_consolidated_authorization_button() -> None:
    ui = Path(
        "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    assert "consolidatedEpisodeProductionV2Button" in ui
    assert "تفويض موحد وبدء إنتاج الحلقة كاملة" in ui
    assert "ConsolidatedEpisodeProductionThread" in ui
