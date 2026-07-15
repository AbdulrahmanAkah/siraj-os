def test_evidence_resolution_integration(
    evidence_resolution_runtime,
    evidence_resolution_plan,
    evidence_resolution_inputs,
):
    result = evidence_resolution_runtime.build_resolution_result(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
    )

    assert result.result_id.startswith("evidence_resolution_result_")
    assert result.validation_state == "VALID"
    assert result.resolved_evidence
