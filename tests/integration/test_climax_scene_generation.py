def test_scene_plan_has_exactly_one_climax_scene(
    scene_planner,
    narration_planner,
    script_structure,
):
    narration_plan = narration_planner.build_narration_plan(script_structure)
    scene_plan = scene_planner.build_scene_plan(narration_plan)

    assert sum(scene.scene_type == "CLIMAX_SCENE" for scene in scene_plan.scenes) == 1
