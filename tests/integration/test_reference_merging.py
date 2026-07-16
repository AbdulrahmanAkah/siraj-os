from dataclasses import replace

from src.application.claim_extraction.models import ClaimRecord


def test_reference_merging(
    evidence_resolution_runtime,
    evidence_resolution_plan,
    evidence_resolution_inputs,
):
    claims, entities, events, graph, timeline = evidence_resolution_inputs
    duplicate_claim = ClaimRecord(
        claim_id="merged-reference-claim",
        claim_text=claims.claims[0].claim_text,
        evidence=list(claims.claims[0].evidence),
        source_record_ids=list(claims.claims[0].source_record_ids),
    )
    duplicated_claims = replace(
        claims,
        claims=claims.claims + [duplicate_claim],
        claim_count=claims.claim_count + 1,
    )
    result = evidence_resolution_runtime.build_resolution_result(
        evidence_resolution_plan,
        duplicated_claims,
        entities,
        events,
        graph,
        timeline,
    )

    assert any(len(item.references) == 2 for item in result.resolved_evidence)
