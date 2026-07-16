def test_duplicate_claims_are_removed(
    claim_extraction_runtime,
    claim_extraction_plan,
    claim_retrieval_result,
):
    result = claim_extraction_runtime.extract_claims(
        claim_extraction_plan,
        claim_retrieval_result,
    )

    claim_texts = [claim.claim_text for claim in result.claims]
    assert len(claim_texts) == len(set(claim_texts))
    assert result.claim_count == 2
