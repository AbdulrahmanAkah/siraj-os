def test_discovery_channel_assignment_follows_source_types(
    source_discovery_architect,
    visual_source_plan,
):
    expected = {
        "ARCHIVE_PHOTOGRAPH": "PUBLIC_ARCHIVE",
        "MUSEUM_COLLECTION": "MUSEUM_CATALOG",
        "HISTORICAL_DOCUMENT": "LIBRARY_CATALOG",
        "MAP_ARCHIVE": "MAP_REPOSITORY",
        "ACADEMIC_SOURCE": "ACADEMIC_INDEX",
        "ART_RECONSTRUCTION": "ART_COLLECTION",
        "TIMELINE_ASSET": "INTERNAL_ASSET_LIBRARY",
    }

    assert source_discovery_architect.assign_discovery_channels(
        visual_source_plan
    ) == {
        source.source_id: expected[source.source_type]
        for source_bundle in visual_source_plan.bundles
        for source in source_bundle.sources
    }
