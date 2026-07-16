def test_discovery_ordering_follows_source_ordering(
    source_discovery_architect,
    visual_source_plan,
):
    plan = source_discovery_architect.build_source_discovery_plan(
        visual_source_plan
    )

    for bundle, source_bundle in zip(plan.bundles, visual_source_plan.bundles):
        assert [query.source_id for query in bundle.queries] == [
            source.source_id for source in source_bundle.sources
        ]
        assert [query.position for query in bundle.queries] == list(
            range(len(bundle.queries))
        )
