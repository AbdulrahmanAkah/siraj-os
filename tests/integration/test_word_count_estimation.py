def test_word_count_estimation_is_positive_and_deterministic(
    narration_planner,
    script_structure,
):
    first = narration_planner.build_narration_plan(script_structure)
    second = narration_planner.build_narration_plan(script_structure)

    assert first.estimated_total_words == second.estimated_total_words
    assert all(block.estimated_word_count > 0 for block in first.blocks)
