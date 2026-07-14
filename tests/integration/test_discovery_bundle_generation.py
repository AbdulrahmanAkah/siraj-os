def test_discovery_bundle_generation_has_one_bundle_per_source_bundle(
    source_discovery_architect,
    visual_source_plan,
):
    bundles = source_discovery_architect.generate_discovery_bundles(
        visual_source_plan
    )

    assert [bundle.source_bundle_id for bundle in bundles] == [
        source_bundle.bundle_id for source_bundle in visual_source_plan.bundles
    ]
    assert all(bundle.queries for bundle in bundles)
