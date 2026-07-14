def test_composition_role_assignment_follows_scene_types(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    expected = {
        "HOOK_SCENE": "ORIENT",
        "CONTEXT_SCENE": "INFORM",
        "EXPLANATION_SCENE": "FOCUS",
        "REVELATION_SCENE": "DISCOVER",
        "CLIMAX_SCENE": "PEAK",
        "RESOLUTION_SCENE": "CONNECT",
        "LEGACY_SCENE": "REFLECT",
    }

    assert storyboard_architect.assign_composition_roles(scene_plan) == {
        scene.scene_id: expected[scene.scene_type] for scene in scene_plan.scenes
    }
