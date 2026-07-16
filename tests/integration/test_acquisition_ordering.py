def test_acquisition_ordering_follows_discovery_query_order(
    source_acquisition_planner,
    source_discovery_plan,
):
    plan = source_acquisition_planner.build_source_acquisition_plan(
        source_discovery_plan
    )

    for batch, discovery_bundle in zip(plan.batches, source_discovery_plan.bundles):
        assert [target.query_id for target in batch.targets] == [
            query.query_id for query in discovery_bundle.queries
        ]
        assert [target.position for target in batch.targets] == list(
            range(len(batch.targets))
        )
