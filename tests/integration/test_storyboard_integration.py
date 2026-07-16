def test_storyboard_architecture_integrates_into_visual_assets(
    visual_asset_architect,
    storyboard_architect,
    scene_plan,
):
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    assets = visual_asset_architect.build_visual_asset_architecture(storyboard)

    assert assets.storyboard_architecture_id == storyboard.architecture_id
    assert [group.sequence_id for group in assets.asset_groups] == [
        sequence.sequence_id for sequence in storyboard.sequences
    ]
    assert visual_asset_architect.validate_architecture(assets)
