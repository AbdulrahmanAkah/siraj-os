def test_duration_uses_fixed_150_words_per_minute(
    narration_planner,
    script_structure,
):
    plan = narration_planner.build_narration_plan(script_structure)

    assert plan.estimated_duration_seconds == round(
        plan.estimated_total_words / 150 * 60,
        2,
    )
