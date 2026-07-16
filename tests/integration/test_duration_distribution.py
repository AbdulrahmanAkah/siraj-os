def test_frame_duration_distribution_matches_scene_duration(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    architecture = storyboard_architect.build_storyboard_architecture(scene_plan)
    scenes_by_id = {scene.scene_id: scene for scene in scene_plan.scenes}

    assert all(
        sum(frame.duration_seconds for frame in sequence.frames)
        == scenes_by_id[sequence.scene_id].estimated_duration
        for sequence in architecture.sequences
    )
    assert all(
        frame.duration_seconds >= storyboard_architect.MIN_FRAME_DURATION
        for sequence in architecture.sequences
        for frame in sequence.frames
    )
    assert architecture.total_duration == scene_plan.total_duration
