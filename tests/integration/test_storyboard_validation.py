def test_storyboard_validation_rejects_orphan_frames(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    architecture = storyboard_architect.build_storyboard_architecture(scene_plan)

    assert storyboard_architect.validate_storyboard(architecture, scene_plan)
    architecture.sequences[0].frames[0].scene_id = "orphan_scene"
    assert not storyboard_architect.validate_storyboard(architecture, scene_plan)
