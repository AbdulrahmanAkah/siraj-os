def test_structured_metadata_entity_extraction(
    entity_extraction_runtime,
    entity_extraction_architect,
    entity_claim_extraction_result,
):
    plan = entity_extraction_architect.build_entity_extraction_plan(
        entity_claim_extraction_result,
        extraction_strategies=["STRUCTURED_METADATA_ENTITY"],
    )
    result = entity_extraction_runtime.extract_entities(
        plan,
        entity_claim_extraction_result,
    )

    assert {(entity.entity_name, entity.entity_type) for entity in result.entities} == {
        ("John Smith", "PERSON"),
        ("NASA", "ORGANIZATION"),
    }
