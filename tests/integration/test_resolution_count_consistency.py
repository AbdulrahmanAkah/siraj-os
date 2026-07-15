def test_resolution_count_consistency(
    evidence_resolution_runtime,
    evidence_resolution_plan,
    evidence_resolution_inputs,
):
    result = evidence_resolution_runtime.build_resolution_result(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
    )

    assert result.evidence_count == len(result.resolved_evidence)
    assert result.bundle_count == len(result.bundles)
