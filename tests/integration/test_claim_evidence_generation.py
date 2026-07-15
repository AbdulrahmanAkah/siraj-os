def test_every_claim_has_traceable_evidence(
    claim_extraction_runtime,
    claim_extraction_plan,
    claim_retrieval_result,
):
    result = claim_extraction_runtime.extract_claims(
        claim_extraction_plan,
        claim_retrieval_result,
    )

    assert all(claim.evidence for claim in result.claims)
    assert all(
        evidence.record_id in claim.source_record_ids
        for claim in result.claims
        for evidence in claim.evidence
    )
    assert all(
        evidence.supporting_text == claim.claim_text
        for claim in result.claims
        for evidence in claim.evidence
    )
