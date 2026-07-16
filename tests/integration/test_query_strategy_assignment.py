def test_query_strategy_assignment_follows_source_types(
    source_discovery_architect,
    visual_source_plan,
):
    expected = {
        "ARCHIVE_PHOTOGRAPH": "ENTITY_AND_DATE",
        "MUSEUM_COLLECTION": "ENTITY_AND_LOCATION",
        "HISTORICAL_DOCUMENT": "DOCUMENT_TITLE",
        "MAP_ARCHIVE": "ENTITY_AND_LOCATION",
        "ACADEMIC_SOURCE": "SUBJECT_SEARCH",
        "ART_RECONSTRUCTION": "COLLECTION_BROWSE",
        "TIMELINE_ASSET": "METADATA_FILTER",
    }

    assert source_discovery_architect.assign_query_strategies(
        visual_source_plan
    ) == {
        source.source_id: expected[source.source_type]
        for source_bundle in visual_source_plan.bundles
        for source in source_bundle.sources
    }
