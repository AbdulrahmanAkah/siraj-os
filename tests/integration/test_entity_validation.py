from dataclasses import replace


def test_entity_validation(
    entity_extraction_runtime,
    entity_extraction_plan,
    entity_claim_extraction_result,
):
    result = entity_extraction_runtime.extract_entities(
        entity_extraction_plan,
        entity_claim_extraction_result,
    )
    invalid_result = replace(result, entity_count=result.entity_count + 1)

    assert entity_extraction_runtime.validate_extraction(
        entity_extraction_plan,
        entity_claim_extraction_result,
        result,
    )
    assert not entity_extraction_runtime.validate_extraction(
        entity_extraction_plan,
        entity_claim_extraction_result,
        invalid_result,
    )
