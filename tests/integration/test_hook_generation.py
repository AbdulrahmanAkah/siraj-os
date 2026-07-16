def test_narration_plan_has_exactly_one_hook(narration_planner, script_structure):
    plan = narration_planner.build_narration_plan(script_structure)

    assert [block.narration_role for block in plan.blocks].count("HOOK") == 1
