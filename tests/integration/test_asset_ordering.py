def test_asset_ordering_follows_storyboard_frame_order(
    visual_asset_architect,
    storyboard_architect,
    scene_plan,
):
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    architecture = visual_asset_architect.build_visual_asset_architecture(storyboard)

    for group, sequence in zip(architecture.asset_groups, storyboard.sequences):
        assert [asset.frame_id for asset in group.assets] == [
            frame.frame_id for frame in sequence.frames
        ]
        assert [asset.position for asset in group.assets] == list(
            range(len(group.assets))
        )
