def test_duplicate_events_are_removed(
    event_extraction_runtime,
    event_extraction_plan,
    event_claim_extraction_result,
    event_entity_extraction_result,
):
    result = event_extraction_runtime.extract_events(
        event_extraction_plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
    )
    keys = [
        (event.event_type, event.event_title, event.event_date)
        for event in result.events
    ]

    assert len(keys) == len(set(keys))
    assert result.event_count == 4
