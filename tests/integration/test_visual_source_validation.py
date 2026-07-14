def test_visual_source_validation_rejects_orphan_sources(
    visual_source_selector,
    visual_asset_architecture,
):
    plan = visual_source_selector.build_visual_source_plan(
        visual_asset_architecture
    )

    assert visual_source_selector.validate_source_plan(
        plan,
        visual_asset_architecture,
    )
    plan.bundles[0].sources[0].asset_id = "orphan_asset"
    assert not visual_source_selector.validate_source_plan(
        plan,
        visual_asset_architecture,
    )
