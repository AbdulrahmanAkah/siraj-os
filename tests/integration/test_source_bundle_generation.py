def test_source_bundle_generation_has_one_bundle_per_asset_group(
    visual_source_selector,
    visual_asset_architecture,
):
    bundles = visual_source_selector.generate_bundles(visual_asset_architecture)

    assert [bundle.group_id for bundle in bundles] == [
        group.group_id for group in visual_asset_architecture.asset_groups
    ]
    assert all(bundle.sources for bundle in bundles)
