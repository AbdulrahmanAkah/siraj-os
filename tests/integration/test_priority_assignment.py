def test_priority_assignment_follows_frame_types(
    visual_asset_architect,
    storyboard_architect,
    scene_plan,
):
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    expected = {
        "ESTABLISHING": "CRITICAL",
        "CONTEXTUAL": "HIGH",
        "DETAIL": "MEDIUM",
        "REVEAL": "HIGH",
        "CLIMAX": "CRITICAL",
        "TRANSITION": "MEDIUM",
        "CLOSING": "LOW",
    }

    assert visual_asset_architect.assign_priorities(storyboard) == {
        frame.frame_id: expected[frame.frame_type]
        for sequence in storyboard.sequences
        for frame in sequence.frames
    }
