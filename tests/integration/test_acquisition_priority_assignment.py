def test_acquisition_priority_assignment_follows_discovery_channels(
    source_acquisition_planner,
    source_discovery_plan,
):
    expected = {
        "PUBLIC_ARCHIVE": "CRITICAL",
        "MUSEUM_CATALOG": "HIGH",
        "LIBRARY_CATALOG": "HIGH",
        "MAP_REPOSITORY": "MEDIUM",
        "ACADEMIC_INDEX": "HIGH",
        "ART_COLLECTION": "LOW",
        "INTERNAL_ASSET_LIBRARY": "LOW",
    }

    assert source_acquisition_planner.assign_priorities(
        source_discovery_plan
    ) == {
        query.query_id: expected[query.discovery_channel]
        for bundle in source_discovery_plan.bundles
        for query in bundle.queries
    }
