def test_explicit_statement_extraction_uses_marked_fields_only(
    claim_extraction_runtime,
    claim_extraction_architect,
    claim_retrieval_result,
):
    plan = claim_extraction_architect.build_claim_extraction_plan(
        claim_retrieval_result,
        extraction_strategies=["EXPLICIT_STATEMENT"],
    )
    result = claim_extraction_runtime.extract_claims(plan, claim_retrieval_result)

    assert result.claim_count == 1
    assert result.claims[0].claim_text == "Example"
