import pytest
from pathlib import Path

from src.application.siraj_v4_plus_legacy_execution_lock_v1 import (
    LegacyExecutionLockedError,
    block_legacy_execution,
)

def test_legacy_execution_lock_is_fail_closed():
    with pytest.raises(LegacyExecutionLockedError):
        block_legacy_execution("test.surface")

def test_execution_hardening_files_import():
    import src.application.siraj_v4_plus_provider_executor_v1 as module
    assert module.SCHEMA_VERSION == "siraj-v4-plus-provider-executor-v1"

def test_legacy_targets_contain_lock_marker():
    repo = Path(__file__).resolve().parents[1]
    targets = {
        "src/application/desktop_media_execution_v1.py": [
            "execute_runware_item",
            "execute_elevenlabs_item",
        ],
        "src/application/end_to_end_production_v1.py": [
            "run_to_next_human_gate",
        ],
        "src/application/consolidated_episode_production_controller_v2.py": [
            "run_consolidated_production_to_human_gate",
        ],
        "src/application/luna_cinematic_prompt_director_v2.py": [
            "execute_authorized_batch",
        ],
        "src/application/automatic_research_script_storyboard_runner_v1.py": [
            "run_editorial_pipeline",
        ],
        "src/application/autonomous_episode_orchestrator_v1.py": [
            "generate_next_episode_scope",
        ],
    }
    for rel, names in targets.items():
        text = (repo / rel).read_text(
            encoding="utf-8"
        )
        assert (
            "SIRAJ_V4_PLUS_LEGACY_EXECUTION_LOCK"
            in text
        )
        for name in names:
            expected = (
                'block_legacy_execution("'
                + rel
                + "::"
                + name
                + '")'
            )
            assert expected in text
