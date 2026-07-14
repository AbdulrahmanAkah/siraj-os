def test_scene_plan_validation_requires_complete_unique_scenes(
    scene_planner,
    narration_planner,
    script_structure,
):
    narration_plan = narration_planner.build_narration_plan(script_structure)
    scene_plan = scene_planner.build_scene_plan(narration_plan)

    assert scene_planner.validate_scene_plan(scene_plan, narration_plan)
    scene_plan.scenes.append(scene_plan.scenes[0])
    assert not scene_planner.validate_scene_plan(scene_plan, narration_plan)
