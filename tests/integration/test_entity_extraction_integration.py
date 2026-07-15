def test_claim_to_entity_extraction_integration(
    entity_extraction_runtime,
    entity_extraction_plan,
    entity_claim_extraction_result,
):
    result = entity_extraction_runtime.execute_entity_extraction(
        entity_extraction_plan,
        entity_claim_extraction_result,
    )

    assert result.result_id.startswith("entity_extraction_result_")
    assert result.entities
    assert all(entity.source_claim_ids for entity in result.entities)
