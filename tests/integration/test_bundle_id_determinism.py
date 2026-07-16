def test_bundle_id_determinism(
    evidence_resolution_runtime,
    evidence_resolution_plan,
    evidence_resolution_inputs,
):
    first = evidence_resolution_runtime.build_resolution_result(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
    )
    second = evidence_resolution_runtime.build_resolution_result(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
    )

    assert [bundle.bundle_id for bundle in first.bundles] == [
        bundle.bundle_id for bundle in second.bundles
    ]
