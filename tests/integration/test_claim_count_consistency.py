def test_claim_and_candidate_counts_are_consistent(
    claim_extraction_runtime,
    claim_extraction_plan,
    claim_retrieval_result,
):
    result = claim_extraction_runtime.extract_claims(
        claim_extraction_plan,
        claim_retrieval_result,
    )

    assert result.claim_count == len(result.claims)
    assert result.candidate_count == len(result.candidates)
    assert result.claim_count <= claim_extraction_plan.claim_limit
