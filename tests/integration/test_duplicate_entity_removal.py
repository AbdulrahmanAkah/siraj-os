def test_duplicate_entities_are_removed(
    entity_extraction_runtime,
    entity_extraction_plan,
    entity_claim_extraction_result,
):
    result = entity_extraction_runtime.extract_entities(
        entity_extraction_plan,
        entity_claim_extraction_result,
    )
    keys = [(entity.entity_name, entity.entity_type) for entity in result.entities]

    assert len(keys) == len(set(keys))
    assert result.entity_count == 3
