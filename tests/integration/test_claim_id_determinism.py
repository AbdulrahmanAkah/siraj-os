def test_claim_ids_are_deterministic(
    claim_extraction_runtime,
    claim_extraction_plan,
    claim_retrieval_result,
):
    first = claim_extraction_runtime.extract_claims(
        claim_extraction_plan,
        claim_retrieval_result,
    )
    second = claim_extraction_runtime.extract_claims(
        claim_extraction_plan,
        claim_retrieval_result,
    )

    assert first == second
    assert [claim.claim_id for claim in first.claims] == [
        claim.claim_id for claim in second.claims
    ]
