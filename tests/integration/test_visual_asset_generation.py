def test_visual_asset_architecture_generates_ordered_asset_groups(
    visual_asset_architect,
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    architecture = visual_asset_architect.build_visual_asset_architecture(storyboard)

    assert architecture.storyboard_architecture_id == storyboard.architecture_id
    assert len(architecture.asset_groups) == len(storyboard.sequences)
    assert architecture.asset_count == sum(
        len(group.assets) for group in architecture.asset_groups
    )
    assert visual_asset_architect.validate_architecture(architecture, storyboard)


def test_visual_asset_generation_is_deterministic(
    visual_asset_architect,
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)

    assert visual_asset_architect.build_visual_asset_architecture(
        storyboard
    ) == visual_asset_architect.build_visual_asset_architecture(storyboard)
