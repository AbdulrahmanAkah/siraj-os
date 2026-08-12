from pathlib import Path

from src.application.siraj_visual_treatment_normalization_v6_6_r8 import (
    normalize_visual_treatment,
)


def test_static_black_hold_maps_to_local_graphics_without_semantic_change():
    item = {
        "shot_id": "EP002-RH-033",
        "start_seconds": 100.0,
        "end_seconds": 104.0,
        "final_budget_treatment": "STATIC_BLACK_HOLD",
    }
    repaired, changed = normalize_visual_treatment(item)

    assert changed is True
    assert repaired["final_budget_treatment"] == "GRAPHICS"
    assert repaired["graphics_spec"]["kind"] == "STATIC_BLACK_HOLD"
    assert repaired["graphics_spec"]["provider_required"] is False
    assert repaired["contains_people"] is False
    assert repaired["runware_positive_prompt_en"]


def test_media_queue_has_treatment_normalizer_defense_in_depth():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/siraj_media_queue_v6_2_1.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_VISUAL_TREATMENT_NORMALIZATION_V6_6_R8" in source
    assert "normalize_visual_treatments" in source


def test_r6_structural_validator_normalizes_before_queue_validation():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_alignment_structural_repair_v6_6_r6.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_VISUAL_TREATMENT_NORMALIZATION_V6_6_R8" in source
    assert "items = normalize_visual_treatments(items)" in source


def test_provider_executor_has_local_black_hold_renderer():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_provider_execution_v6_2_1.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_STATIC_BLACK_HOLD_LOCAL_RENDERER_V6_6_R8" in source
    assert "render_static_black_hold" in source
    assert "is_static_black_hold_spec" in source


def test_r3_contract_forbids_noncanonical_treatments():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_alignment_semantic_autorepair_v6_6_r3.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_R3_CANONICAL_VISUAL_TREATMENTS_V6_6_R8" in source
    assert "ANIMATED_STILL_COMPOSITING" in source
    assert "GENERATED_VIDEO" in source
    assert "GRAPHICS" in source
