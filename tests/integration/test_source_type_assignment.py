def test_source_type_assignment_follows_asset_types(
    visual_source_selector,
    visual_asset_architecture,
):
    expected = {
        "HISTORICAL_PERSON": "ARCHIVE_PHOTOGRAPH",
        "HISTORICAL_LOCATION": "MUSEUM_COLLECTION",
        "HISTORICAL_OBJECT": "MUSEUM_COLLECTION",
        "DOCUMENT": "HISTORICAL_DOCUMENT",
        "MAP": "MAP_ARCHIVE",
        "TIMELINE_GRAPHIC": "TIMELINE_ASSET",
        "ARTWORK": "ART_RECONSTRUCTION",
    }

    assert visual_source_selector.assign_source_types(
        visual_asset_architecture
    ) == {
        asset.asset_id: expected[asset.asset_type]
        for group in visual_asset_architecture.asset_groups
        for asset in group.assets
    }
