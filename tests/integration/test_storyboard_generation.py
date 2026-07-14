def test_storyboard_architecture_generates_ordered_sequences(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )
    architecture = storyboard_architect.build_storyboard_architecture(scene_plan)

    assert architecture.scene_plan_id == scene_plan.plan_id
    assert len(architecture.sequences) == len(scene_plan.scenes)
    assert architecture.frame_count == sum(
        len(sequence.frames) for sequence in architecture.sequences
    )
    assert storyboard_architect.validate_storyboard(architecture, scene_plan)


def test_storyboard_generation_is_deterministic(
    storyboard_architect,
    scene_planner,
    narration_planner,
    script_structure,
):
    scene_plan = scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )

    assert storyboard_architect.build_storyboard_architecture(
        scene_plan
    ) == storyboard_architect.build_storyboard_architecture(scene_plan)
