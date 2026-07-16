def test_frame_generation_covers_every_scene(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    frames = storyboard_architect.generate_frames(scene_plan)

    assert len(frames) >= len(scene_plan.scenes)
    assert [frame.scene_id for frame in frames] == [
        scene.scene_id for scene in scene_plan.scenes
    ]
    assert [frame.position for frame in frames] == [0] * len(frames)
