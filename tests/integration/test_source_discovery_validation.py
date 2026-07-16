def test_source_discovery_validation_rejects_orphan_queries(
    source_discovery_architect,
    visual_source_plan,
):
    plan = source_discovery_architect.build_source_discovery_plan(
        visual_source_plan
    )

    assert source_discovery_architect.validate_discovery_plan(
        plan,
        visual_source_plan,
    )
    plan.bundles[0].queries[0].source_id = "orphan_source"
    assert not source_discovery_architect.validate_discovery_plan(
        plan,
        visual_source_plan,
    )
