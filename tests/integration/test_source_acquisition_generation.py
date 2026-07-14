def test_source_acquisition_plan_generates_ordered_batches(
    source_acquisition_planner,
    source_discovery_plan,
):
    plan = source_acquisition_planner.build_source_acquisition_plan(
        source_discovery_plan
    )

    assert plan.source_discovery_plan_id == source_discovery_plan.plan_id
    assert len(plan.batches) == len(source_discovery_plan.bundles)
    assert plan.target_count == sum(
        len(batch.targets) for batch in plan.batches
    )
    assert source_acquisition_planner.validate_acquisition_plan(
        plan,
        source_discovery_plan,
    )


def test_source_acquisition_generation_is_deterministic(
    source_acquisition_planner,
    source_discovery_plan,
):
    assert source_acquisition_planner.build_source_acquisition_plan(
        source_discovery_plan
    ) == source_acquisition_planner.build_source_acquisition_plan(
        source_discovery_plan
    )
