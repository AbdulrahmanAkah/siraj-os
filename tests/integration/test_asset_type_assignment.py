def test_asset_type_assignment_follows_frame_types(
    visual_asset_architect,
    storyboard_architect,
    scene_plan,
):
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    expected = {
        "ESTABLISHING": "HISTORICAL_LOCATION",
        "CONTEXTUAL": "MAP",
        "DETAIL": "HISTORICAL_OBJECT",
        "REVEAL": "DOCUMENT",
        "CLIMAX": "HISTORICAL_PERSON",
        "TRANSITION": "TIMELINE_GRAPHIC",
        "CLOSING": "ARTWORK",
    }

    assert visual_asset_architect.assign_asset_types(storyboard) == {
        frame.frame_id: expected[frame.frame_type]
        for sequence in storyboard.sequences
        for frame in sequence.frames
    }
