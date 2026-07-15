def test_entity_derived_event_extraction(
    event_extraction_runtime,
    event_extraction_architect,
    event_claim_extraction_result,
    event_entity_extraction_result,
):
    plan = event_extraction_architect.build_event_extraction_plan(
        event_claim_extraction_result,
        event_entity_extraction_result,
        extraction_strategies=["ENTITY_DERIVED_EVENT"],
    )
    result = event_extraction_runtime.extract_events(
        plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
    )

    assert {
        (event.event_type, event.event_title)
        for event in result.events
    } == {
        ("DATE_EVENT", "Date: 2024-01-01"),
        ("ORGANIZATION_EVENT", "Organization: NASA"),
        ("LOCATION_EVENT", "Location: Cairo"),
    }
