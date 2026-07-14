def test_source_ordering_follows_asset_ordering(
    visual_source_selector,
    visual_asset_architecture,
):
    plan = visual_source_selector.build_visual_source_plan(
        visual_asset_architecture
    )

    for bundle, group in zip(plan.bundles, visual_asset_architecture.asset_groups):
        assert [source.asset_id for source in bundle.sources] == [
            asset.asset_id for asset in group.assets
        ]
        assert [source.position for source in bundle.sources] == list(
            range(len(bundle.sources))
        )
