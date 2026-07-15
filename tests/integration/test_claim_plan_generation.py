def test_claim_extraction_plan_generation(
    claim_extraction_plan,
    claim_retrieval_result,
):
    assert claim_extraction_plan.retrieval_id == claim_retrieval_result.retrieval_id
    assert claim_extraction_plan.extraction_strategies == [
        "EXPLICIT_STATEMENT",
        "STRUCTURED_METADATA",
        "TITLE_DERIVED",
    ]
    assert claim_extraction_plan.claim_limit > 0
