def test_entity_ids_are_deterministic(
    entity_extraction_runtime,
    entity_extraction_plan,
    entity_claim_extraction_result,
):
    first = entity_extraction_runtime.extract_entities(
        entity_extraction_plan,
        entity_claim_extraction_result,
    )
    second = entity_extraction_runtime.extract_entities(
        entity_extraction_plan,
        entity_claim_extraction_result,
    )

    assert first == second
    assert [entity.entity_id for entity in first.entities] == [
        entity.entity_id for entity in second.entities
    ]
