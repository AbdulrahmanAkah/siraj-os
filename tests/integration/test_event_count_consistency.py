def test_event_and_candidate_counts_are_consistent(
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

    assert result.event_count == len(result.events)
    assert result.candidate_count == len(result.candidates)
    assert result.event_count <= event_extraction_plan.event_limit
