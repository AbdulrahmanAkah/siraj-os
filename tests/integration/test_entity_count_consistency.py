def test_entity_and_candidate_counts_are_consistent(
    entity_extraction_runtime,
    entity_extraction_plan,
    entity_claim_extraction_result,
):
    result = entity_extraction_runtime.extract_entities(
        entity_extraction_plan,
        entity_claim_extraction_result,
    )

    assert result.entity_count == len(result.entities)
    assert result.candidate_count == len(result.candidates)
    assert result.entity_count <= entity_extraction_plan.entity_limit
