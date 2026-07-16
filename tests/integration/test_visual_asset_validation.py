def test_visual_asset_validation_rejects_orphan_assets(
    visual_asset_architect,
    storyboard_architect,
    scene_plan,
):
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    architecture = visual_asset_architect.build_visual_asset_architecture(storyboard)

    assert visual_asset_architect.validate_architecture(architecture, storyboard)
    architecture.asset_groups[0].assets[0].frame_id = "orphan_frame"
    assert not visual_asset_architect.validate_architecture(
        architecture,
        storyboard,
    )
