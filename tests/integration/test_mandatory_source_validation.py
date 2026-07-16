def test_source_plan_requires_mandatory_source(
    visual_source_selector,
    visual_asset_architecture,
):
    plan = visual_source_selector.build_visual_source_plan(
        visual_asset_architecture
    )

    assert any(
        source.source_priority == "MANDATORY"
        for bundle in plan.bundles
        for source in bundle.sources
    )
    for bundle in plan.bundles:
        for source in bundle.sources:
            source.source_priority = "OPTIONAL"
    assert not visual_source_selector.validate_source_plan(
        plan,
        visual_asset_architecture,
    )
