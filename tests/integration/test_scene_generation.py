def test_scene_planner_generates_one_ordered_scene_per_narration_block(
    scene_planner,
    narration_planner,
    script_structure,
):
    narration_plan = narration_planner.build_narration_plan(script_structure)
    scenes = scene_planner.generate_scenes(narration_plan)

    assert len(scenes) == len(narration_plan.blocks)
    assert [scene.position for scene in scenes] == list(range(len(scenes)))
    assert [scene.block_id for scene in scenes] == [
        block.block_id for block in narration_plan.blocks
    ]
    assert all(scene.scene_id.startswith("scene_") for scene in scenes)


def test_scene_generation_is_deterministic(scene_planner, narration_planner, script_structure):
    narration_plan = narration_planner.build_narration_plan(script_structure)

    assert scene_planner.build_scene_plan(narration_plan) == scene_planner.build_scene_plan(
        narration_plan
    )
