def test_scene_type_assignment_follows_narration_roles(
    scene_planner,
    narration_planner,
    script_structure,
):
    narration_plan = narration_planner.build_narration_plan(script_structure)

    expected = {
        "HOOK": "HOOK_SCENE",
        "CONTEXT": "CONTEXT_SCENE",
        "EXPLANATION": "EXPLANATION_SCENE",
        "REVELATION": "REVELATION_SCENE",
        "CLIMAX_NARRATION": "CLIMAX_SCENE",
        "RESOLUTION": "RESOLUTION_SCENE",
        "LEGACY_REFLECTION": "LEGACY_SCENE",
    }
    assert scene_planner.assign_scene_types(narration_plan) == {
        block.block_id: expected[block.narration_role]
        for block in narration_plan.blocks
    }
