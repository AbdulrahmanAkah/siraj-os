def test_structured_metadata_extraction_is_deterministic(
    claim_extraction_runtime,
    claim_extraction_architect,
    claim_retrieval_result,
):
    plan = claim_extraction_architect.build_claim_extraction_plan(
        claim_retrieval_result,
        extraction_strategies=["STRUCTURED_METADATA"],
    )
    result = claim_extraction_runtime.extract_claims(plan, claim_retrieval_result)

    assert result.claim_count == 1
    assert result.claims[0].claim_text == "Title is Example"
