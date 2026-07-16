def test_frame_type_assignment_follows_scene_types(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    expected = {
        "HOOK_SCENE": "ESTABLISHING",
        "CONTEXT_SCENE": "CONTEXTUAL",
        "EXPLANATION_SCENE": "DETAIL",
        "REVELATION_SCENE": "REVEAL",
        "CLIMAX_SCENE": "CLIMAX",
        "RESOLUTION_SCENE": "TRANSITION",
        "LEGACY_SCENE": "CLOSING",
    }

    assert storyboard_architect.assign_frame_types(scene_plan) == {
        scene.scene_id: expected[scene.scene_type] for scene in scene_plan.scenes
    }
