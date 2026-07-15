from dataclasses import replace

from src.application.claim_extraction.models import ClaimRecord


def test_duplicate_evidence_resolution(
    evidence_resolution_runtime,
    evidence_resolution_plan,
    evidence_resolution_inputs,
):
    claims, entities, events, graph, timeline = evidence_resolution_inputs
    duplicate_claim = ClaimRecord(
        claim_id="duplicate-claim",
        claim_text=claims.claims[0].claim_text,
        evidence=list(claims.claims[0].evidence),
        source_record_ids=list(claims.claims[0].source_record_ids),
    )
    duplicated_claims = replace(
        claims,
        claims=claims.claims + [duplicate_claim],
        claim_count=claims.claim_count + 1,
    )
    collected = evidence_resolution_runtime.collect_evidence(
        evidence_resolution_plan,
        duplicated_claims,
        entities,
        events,
        graph,
        timeline,
    )
    resolved = evidence_resolution_runtime.resolve_duplicates(collected)

    assert len(resolved) < len(collected)
