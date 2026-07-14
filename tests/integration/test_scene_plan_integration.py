def test_scene_plan_integrates_into_storyboard_architecture(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    narration = narration_planner.build_narration_plan(script_structure)
    scene_plan = scene_planner.build_scene_plan(narration)
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)

    assert storyboard.scene_plan_id == scene_plan.plan_id
    assert [sequence.scene_id for sequence in storyboard.sequences] == [
        scene.scene_id for scene in scene_plan.scenes
    ]
    assert storyboard_architect.validate_storyboard(storyboard)
