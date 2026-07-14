def test_asset_role_assignment_follows_frame_types(
    visual_asset_architect,
    storyboard_architect,
    scene_plan,
):
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    expected = {
        "ESTABLISHING": "PRIMARY",
        "CONTEXTUAL": "CONTEXT",
        "DETAIL": "SUPPORTING",
        "REVEAL": "EVIDENCE",
        "CLIMAX": "PRIMARY",
        "TRANSITION": "TRANSITION",
        "CLOSING": "CONTEXT",
    }

    assert visual_asset_architect.assign_asset_roles(storyboard) == {
        frame.frame_id: expected[frame.frame_type]
        for sequence in storyboard.sequences
        for frame in sequence.frames
    }
