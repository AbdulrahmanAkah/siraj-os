def test_source_discovery_plan_integrates_into_acquisition_plan(
    source_acquisition_planner,
    source_discovery_plan,
):
    plan = source_acquisition_planner.build_source_acquisition_plan(
        source_discovery_plan
    )

    assert plan.source_discovery_plan_id == source_discovery_plan.plan_id
    assert source_acquisition_planner.validate_acquisition_plan(plan)
