def test_every_entity_has_claim_evidence(
    entity_extraction_runtime,
    entity_extraction_plan,
    entity_claim_extraction_result,
):
    result = entity_extraction_runtime.extract_entities(
        entity_extraction_plan,
        entity_claim_extraction_result,
    )

    assert all(entity.evidence for entity in result.entities)
    assert all(
        evidence.claim_id in entity.source_claim_ids
        for entity in result.entities
        for evidence in entity.evidence
    )
    assert all(
        evidence.supporting_text
        for entity in result.entities
        for evidence in entity.evidence
    )
