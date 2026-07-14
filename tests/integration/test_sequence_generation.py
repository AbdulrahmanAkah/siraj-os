def test_sequence_generation_has_one_sequence_per_scene(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    sequences = storyboard_architect.generate_sequences(scene_plan)

    assert [sequence.scene_id for sequence in sequences] == [
        scene.scene_id for scene in scene_plan.scenes
    ]
    assert all(sequence.frames for sequence in sequences)
