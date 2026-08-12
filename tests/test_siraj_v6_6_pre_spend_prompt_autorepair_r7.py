from pathlib import Path

from src.application.siraj_pre_spend_prompt_autorepair_v6_6_r7 import (
    _normalize_aliases,
    is_pre_spend_duplicate_failure,
)


def test_alias_normalization_maps_visual_prompt_to_runware_prompt():
    items = [
        {
            "shot_id": "S1",
            "visual_prompt_en": "A moonlit desert ridge",
        }
    ]
    count = _normalize_aliases(items)
    assert count == 1
    assert (
        items[0]["runware_positive_prompt_en"]
        == "A moonlit desert ridge"
    )


def test_detects_current_pre_spend_failure():
    exc = RuntimeError(
        'PRE_SPEND_DUPLICATE_GATE_FAILED:'
        '[{"type":"EMPTY_PROMPT","shot_id":"EP002-SH-001"}]'
    )
    assert is_pre_spend_duplicate_failure(exc)


def test_v66_wrapper_has_r7_handler():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/application/siraj_autopilot_v6_6.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_PRE_SPEND_PROMPT_AUTOREPAIR_V6_6_R7" in source
    assert "repair_pre_spend_duplicate_gate" in source
    assert "is_pre_spend_duplicate_failure" in source


def test_r3_contract_requires_executable_prompts():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_alignment_semantic_autorepair_v6_6_r3.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_R3_EXECUTABLE_PROMPT_CONTRACT_V6_6_R7" in source
    assert "runware_positive_prompt_en" in source
    assert "runware_negative_prompt_en" in source


def test_paid_retry_law_unchanged():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_episode_master_authorization_v6_6.py"
    ).read_text(encoding="utf-8-sig")

    assert "PAID_RETRY_CONFIRMATION_PHRASE" in source
    assert "automatic_paid_retry" in source
    assert "automatic_paid_resubmission" in source
