def test_visual_asset_architecture_integrates_into_source_plan(
    visual_source_selector,
    visual_asset_architecture,
):
    plan = visual_source_selector.build_visual_source_plan(
        visual_asset_architecture
    )

    assert plan.visual_asset_architecture_id == visual_asset_architecture.architecture_id
    assert visual_source_selector.validate_source_plan(plan)
