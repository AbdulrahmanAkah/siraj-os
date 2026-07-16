def test_asset_group_generation_has_one_group_per_sequence(
    visual_asset_architect,
    storyboard_architect,
    scene_plan,
):
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    groups = visual_asset_architect.generate_asset_groups(storyboard)

    assert [group.sequence_id for group in groups] == [
        sequence.sequence_id for sequence in storyboard.sequences
    ]
    assert all(group.assets for group in groups)
