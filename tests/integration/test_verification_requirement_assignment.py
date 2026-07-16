def test_verification_assignment_follows_discovery_channels(
    source_acquisition_planner,
    source_discovery_plan,
):
    expected = {
        "PUBLIC_ARCHIVE": "STRICT_VERIFICATION",
        "MUSEUM_CATALOG": "STRICT_VERIFICATION",
        "LIBRARY_CATALOG": "STRICT_VERIFICATION",
        "MAP_REPOSITORY": "STANDARD_VERIFICATION",
        "ACADEMIC_INDEX": "STRICT_VERIFICATION",
        "ART_COLLECTION": "STANDARD_VERIFICATION",
        "INTERNAL_ASSET_LIBRARY": "BASIC_VERIFICATION",
    }

    assert source_acquisition_planner.assign_verification_requirements(
        source_discovery_plan
    ) == {
        query.query_id: expected[query.discovery_channel]
        for bundle in source_discovery_plan.bundles
        for query in bundle.queries
    }
