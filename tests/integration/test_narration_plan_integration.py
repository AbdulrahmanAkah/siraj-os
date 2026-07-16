def test_narration_plan_integrates_into_scene_plan(
    narration_planner,
    script_structure,
    scene_planner,
):
    narration = narration_planner.build_narration_plan(script_structure)
    scene_plan = scene_planner.build_scene_plan(narration)

    assert scene_plan.narration_plan_id == narration.plan_id
    assert scene_plan.scene_count == len(narration.blocks)
    assert scene_plan.total_duration == sum(
        scene.estimated_duration for scene in scene_plan.scenes
    )
    assert scene_planner.validate_scene_plan(scene_plan)
