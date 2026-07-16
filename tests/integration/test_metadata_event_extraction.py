def test_metadata_event_extraction(
    event_extraction_runtime,
    event_extraction_architect,
    event_claim_extraction_result,
    event_entity_extraction_result,
):
    plan = event_extraction_architect.build_event_extraction_plan(
        event_claim_extraction_result,
        event_entity_extraction_result,
        extraction_strategies=["METADATA_EVENT"],
    )
    result = event_extraction_runtime.extract_events(
        plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
    )

    assert {
        event.event_type for event in result.events
    } == {"PUBLICATION_EVENT", "ORGANIZATION_EVENT", "LOCATION_EVENT"}
