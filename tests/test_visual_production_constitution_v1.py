from __future__ import annotations

import json

from src.application.visual_production_constitution_v1 import (
    CONSTITUTION_VERSION,
    compile_visual_prompt,
    load_visual_production_constitution,
    validate_repair_storyboard,
)


def test_series_constitution_loads_and_hashes() -> None:
    constitution = load_visual_production_constitution(
        __import__("pathlib").Path(__file__).parents[1]
    )
    assert constitution.version == CONSTITUTION_VERSION
    assert len(constitution.sha256) == 64
    assert constitution.data["GRAPHICS_FORBIDDEN"] is True
    assert constitution.data["FEMALE_MODESTY_MAXIMUM_STRICT"]["VISIBLE_HANDS_PREFERRED"] is False


def test_prompt_compiler_carries_strict_female_contract() -> None:
    constitution = load_visual_production_constitution(
        __import__("pathlib").Path(__file__).parents[1]
    )
    compiled = compile_visual_prompt(
        constitution,
        "Two fully covered figures visibly kneel and bow in supplication.",
        "faces, exposed skin, extra characters",
        includes_female=True,
    )
    assert "GRAPHICS_ALLOWED=FALSE" in compiled["positive_prompt"]
    assert "FEMALE_VISIBLE_HAIR=FORBIDDEN" in compiled["positive_prompt"]
    assert "FEMALE_VISIBLE_ARMS=FORBIDDEN" in compiled["positive_prompt"]
    assert "body-shaped silhouette" in compiled["positive_prompt"]


def test_storyboard_validator_blocks_approved_or_graphic_plan(tmp_path) -> None:
    constitution_path = tmp_path / "constitution.json"
    source = json.loads(
        (__import__("pathlib").Path(__file__).parents[1]
         / "projects/_series/siraj-visual-production-constitution-v1.json")
        .read_text(encoding="utf-8")
    )
    constitution_path.write_text(json.dumps(source), encoding="utf-8")
    constitution = load_visual_production_constitution(
        __import__("pathlib").Path(__file__).parents[1], constitution_path
    )
    result = validate_repair_storyboard(
        {
            "AUDIO_IS_DURATION_AUTHORITY": True,
            "VISUAL_GENERATION_ALLOWED": True,
            "APPROVED_STORYBOARD_SHA256": "already-approved",
            "PLANNED_GRAPHICS_COUNT": 1,
            "timeline_shots": [],
        },
        constitution,
    )
    assert result["status"] == "FAIL"
    assert "VISUAL_GENERATION_MUST_BE_FALSE" in result["errors"]
    assert "APPROVED_STORYBOARD_SHA256_MUST_BE_NULL" in result["errors"]
    assert "PLANNED_GRAPHICS_COUNT_MUST_BE_ZERO" in result["errors"]
