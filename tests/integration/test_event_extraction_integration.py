def test_claim_entity_event_extraction_integration(
    event_extraction_runtime,
    event_extraction_plan,
    event_claim_extraction_result,
    event_entity_extraction_result,
):
    result = event_extraction_runtime.execute_event_extraction(
        event_extraction_plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
    )

    assert result.result_id.startswith("event_extraction_result_")
    assert result.events
    assert all(event.source_claim_ids or event.source_entity_ids for event in result.events)
