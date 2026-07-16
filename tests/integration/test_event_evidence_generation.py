def test_every_event_has_traceable_evidence(
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

    assert all(event.evidence for event in result.events)
    assert all(
        evidence.claim_ids or evidence.entity_ids
        for event in result.events
        for evidence in event.evidence
    )
    assert all(
        evidence.supporting_text == event.event_title
        for event in result.events
        for evidence in event.evidence
    )
