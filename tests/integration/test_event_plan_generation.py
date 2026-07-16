def test_event_extraction_plan_generation(
    event_extraction_plan,
    event_claim_extraction_result,
    event_entity_extraction_result,
):
    assert event_extraction_plan.claim_extraction_result_id == (
        event_claim_extraction_result.result_id
    )
    assert event_extraction_plan.entity_extraction_result_id == (
        event_entity_extraction_result.result_id
    )
    assert event_extraction_plan.extraction_strategies == [
        "METADATA_EVENT",
        "CLAIM_PATTERN_EVENT",
        "ENTITY_DERIVED_EVENT",
    ]
