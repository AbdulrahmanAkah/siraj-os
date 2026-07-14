def test_source_discovery_plan_generates_ordered_bundles(
    source_discovery_architect,
    visual_source_plan,
):
    plan = source_discovery_architect.build_source_discovery_plan(
        visual_source_plan
    )

    assert plan.visual_source_plan_id == visual_source_plan.plan_id
    assert len(plan.bundles) == len(visual_source_plan.bundles)
    assert plan.query_count == sum(
        len(bundle.queries) for bundle in plan.bundles
    )
    assert source_discovery_architect.validate_discovery_plan(
        plan,
        visual_source_plan,
    )


def test_source_discovery_generation_is_deterministic(
    source_discovery_architect,
    visual_source_plan,
):
    assert source_discovery_architect.build_source_discovery_plan(
        visual_source_plan
    ) == source_discovery_architect.build_source_discovery_plan(visual_source_plan)
