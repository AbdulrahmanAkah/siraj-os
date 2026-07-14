def test_acquisition_batch_generation_has_one_batch_per_discovery_bundle(
    source_acquisition_planner,
    source_discovery_plan,
):
    batches = source_acquisition_planner.generate_batches(source_discovery_plan)

    assert [batch.discovery_bundle_id for batch in batches] == [
        bundle.bundle_id for bundle in source_discovery_plan.bundles
    ]
    assert all(batch.targets for batch in batches)
