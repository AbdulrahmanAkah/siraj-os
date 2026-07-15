from dataclasses import replace


def test_resolution_validation(
    evidence_resolution_runtime,
    evidence_resolution_plan,
    evidence_resolution_inputs,
):
    result = evidence_resolution_runtime.build_resolution_result(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
    )
    invalid = replace(result, evidence_count=result.evidence_count + 1)

    assert evidence_resolution_runtime.validate_resolution(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
        result,
    )
    assert not evidence_resolution_runtime.validate_resolution(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
        invalid,
    )
