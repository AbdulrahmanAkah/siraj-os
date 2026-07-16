def test_retrieval_to_claim_extraction_integration(
    claim_extraction_runtime,
    claim_extraction_plan,
    claim_retrieval_result,
):
    result = claim_extraction_runtime.execute_claim_extraction(
        claim_extraction_plan,
        claim_retrieval_result,
    )

    assert result.result_id.startswith("claim_extraction_result_")
    assert result.claims
    assert all(claim.source_record_ids for claim in result.claims)
