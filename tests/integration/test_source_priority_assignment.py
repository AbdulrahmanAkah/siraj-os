def test_source_priority_assignment_follows_asset_types(
    visual_source_selector,
    visual_asset_architecture,
):
    expected = {
        "HISTORICAL_PERSON": "MANDATORY",
        "HISTORICAL_LOCATION": "MANDATORY",
        "HISTORICAL_OBJECT": "PREFERRED",
        "DOCUMENT": "MANDATORY",
        "MAP": "PREFERRED",
        "TIMELINE_GRAPHIC": "OPTIONAL",
        "ARTWORK": "OPTIONAL",
    }

    assert visual_source_selector.assign_priorities(
        visual_asset_architecture
    ) == {
        asset.asset_id: expected[asset.asset_type]
        for group in visual_asset_architecture.asset_groups
        for asset in group.assets
    }
