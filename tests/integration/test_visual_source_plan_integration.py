def test_visual_source_plan_integrates_into_discovery_architecture(
    source_discovery_architect,
    visual_source_plan,
):
    plan = source_discovery_architect.build_source_discovery_plan(
        visual_source_plan
    )

    assert plan.visual_source_plan_id == visual_source_plan.plan_id
    assert source_discovery_architect.validate_discovery_plan(plan)
