def test_visual_role_assignment_follows_narration_roles(
    scene_planner,
    narration_planner,
    script_structure,
):
    narration_plan = narration_planner.build_narration_plan(script_structure)

    expected = {
        "HOOK": "ATTENTION",
        "CONTEXT": "ORIENTATION",
        "EXPLANATION": "EXPLANATION",
        "REVELATION": "DISCOVERY",
        "CLIMAX_NARRATION": "PEAK",
        "RESOLUTION": "AFTERMATH",
        "LEGACY_REFLECTION": "REFLECTION",
    }
    assert scene_planner.assign_visual_roles(narration_plan) == {
        block.block_id: expected[block.narration_role]
        for block in narration_plan.blocks
    }
