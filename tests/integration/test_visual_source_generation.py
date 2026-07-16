def test_visual_source_plan_generates_ordered_bundles(
    visual_source_selector,
    visual_asset_architecture,
):
    plan = visual_source_selector.build_visual_source_plan(
        visual_asset_architecture
    )

    assert plan.visual_asset_architecture_id == visual_asset_architecture.architecture_id
    assert len(plan.bundles) == len(visual_asset_architecture.asset_groups)
    assert plan.source_count == sum(
        len(bundle.sources) for bundle in plan.bundles
    )
    assert visual_source_selector.validate_source_plan(
        plan,
        visual_asset_architecture,
    )


def test_visual_source_generation_is_deterministic(
    visual_source_selector,
    visual_asset_architecture,
):
    assert visual_source_selector.build_visual_source_plan(
        visual_asset_architecture
    ) == visual_source_selector.build_visual_source_plan(visual_asset_architecture)
