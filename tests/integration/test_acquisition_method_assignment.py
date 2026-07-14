def test_acquisition_method_assignment_follows_discovery_channels(
    source_acquisition_planner,
    source_discovery_plan,
):
    expected = {
        "PUBLIC_ARCHIVE": "ARCHIVE_REQUEST",
        "MUSEUM_CATALOG": "CATALOG_LOOKUP",
        "LIBRARY_CATALOG": "DOCUMENT_RETRIEVAL",
        "MAP_REPOSITORY": "MAP_RETRIEVAL",
        "ACADEMIC_INDEX": "ACADEMIC_LOOKUP",
        "ART_COLLECTION": "COLLECTION_REVIEW",
        "INTERNAL_ASSET_LIBRARY": "INTERNAL_FETCH",
    }

    assert source_acquisition_planner.assign_acquisition_methods(
        source_discovery_plan
    ) == {
        query.query_id: expected[query.discovery_channel]
        for bundle in source_discovery_plan.bundles
        for query in bundle.queries
    }
