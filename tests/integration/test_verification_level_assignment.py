def test_verification_level_assignment_follows_source_types(
    source_discovery_architect,
    visual_source_plan,
):
    expected = {
        "ARCHIVE_PHOTOGRAPH": "STRICT",
        "MUSEUM_COLLECTION": "STRICT",
        "HISTORICAL_DOCUMENT": "STRICT",
        "MAP_ARCHIVE": "STANDARD",
        "ACADEMIC_SOURCE": "STRICT",
        "ART_RECONSTRUCTION": "STANDARD",
        "TIMELINE_ASSET": "BASIC",
    }

    assert source_discovery_architect.assign_verification_levels(
        visual_source_plan
    ) == {
        source.source_id: expected[source.source_type]
        for source_bundle in visual_source_plan.bundles
        for source in source_bundle.sources
    }
