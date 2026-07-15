def test_claim_pattern_event_extraction(
    event_extraction_runtime,
    event_extraction_architect,
    event_claim_extraction_result,
    event_entity_extraction_result,
):
    plan = event_extraction_architect.build_event_extraction_plan(
        event_claim_extraction_result,
        event_entity_extraction_result,
        extraction_strategies=["CLAIM_PATTERN_EVENT"],
    )
    result = event_extraction_runtime.extract_events(
        plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
    )

    assert result.event_count == 1
    assert result.events[0].event_type == "PUBLICATION_EVENT"
    assert result.events[0].event_date == "2024-01-01"
