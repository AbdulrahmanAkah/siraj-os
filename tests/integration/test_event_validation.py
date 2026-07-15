from dataclasses import replace


def test_event_validation(
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
    invalid_result = replace(result, event_count=result.event_count + 1)

    assert event_extraction_runtime.validate_extraction(
        event_extraction_plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
        result,
    )
    assert not event_extraction_runtime.validate_extraction(
        event_extraction_plan,
        event_claim_extraction_result,
        event_entity_extraction_result,
        invalid_result,
    )
