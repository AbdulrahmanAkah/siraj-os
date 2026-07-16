def test_source_acquisition_validation_rejects_orphan_targets(
    source_acquisition_planner,
    source_discovery_plan,
):
    plan = source_acquisition_planner.build_source_acquisition_plan(
        source_discovery_plan
    )

    assert source_acquisition_planner.validate_acquisition_plan(
        plan,
        source_discovery_plan,
    )
    plan.batches[0].targets[0].query_id = "orphan_query"
    assert not source_acquisition_planner.validate_acquisition_plan(
        plan,
        source_discovery_plan,
    )
