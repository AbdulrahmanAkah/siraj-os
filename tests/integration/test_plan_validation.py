def test_narration_plan_validation_requires_unique_complete_blocks(
    narration_planner,
    script_structure,
):
    plan = narration_planner.build_narration_plan(script_structure)

    assert narration_planner.validate_plan(plan)
    plan.blocks.append(plan.blocks[0])
    assert not narration_planner.validate_plan(plan)
