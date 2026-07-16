def test_event_ids_are_deterministic(
    event_extraction_runtime,
    event_extraction_plan,
    event_claim_extraction_result,
    event_entity_extraction_result,
):
    first = event_extraction_runtime.extract_events(
        event_extraction_plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
    )
    second = event_extraction_runtime.extract_events(
        event_extraction_plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
    )

    assert first == second
    assert [event.event_id for event in first.events] == [
        event.event_id for event in second.events
    ]
