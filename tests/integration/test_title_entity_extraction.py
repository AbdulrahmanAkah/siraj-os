def test_title_entity_extraction(
    entity_extraction_runtime,
    entity_extraction_architect,
    entity_claim_extraction_result,
):
    plan = entity_extraction_architect.build_entity_extraction_plan(
        entity_claim_extraction_result,
        extraction_strategies=["TITLE_ENTITY"],
    )
    result = entity_extraction_runtime.extract_entities(
        plan,
        entity_claim_extraction_result,
    )

    assert result.entity_count == 1
    assert result.entities[0].entity_name == "The Odyssey"
    assert result.entities[0].entity_type == "WORK"
