def test_entity_extraction_plan_generation(
    entity_extraction_plan,
    entity_claim_extraction_result,
):
    assert entity_extraction_plan.claim_extraction_result_id == (
        entity_claim_extraction_result.result_id
    )
    assert entity_extraction_plan.extraction_strategies == [
        "STRUCTURED_METADATA_ENTITY",
        "CLAIM_PATTERN_ENTITY",
        "TITLE_ENTITY",
    ]
    assert entity_extraction_plan.entity_limit > 0
