from dataclasses import replace


def test_claim_extraction_validation(
    claim_extraction_runtime,
    claim_extraction_plan,
    claim_retrieval_result,
):
    result = claim_extraction_runtime.extract_claims(
        claim_extraction_plan,
        claim_retrieval_result,
    )
    invalid_result = replace(result, claim_count=result.claim_count + 1)

    assert claim_extraction_runtime.validate_extraction(
        claim_extraction_plan,
        claim_retrieval_result,
        result,
    )
    assert not claim_extraction_runtime.validate_extraction(
        claim_extraction_plan,
        claim_retrieval_result,
        invalid_result,
    )
