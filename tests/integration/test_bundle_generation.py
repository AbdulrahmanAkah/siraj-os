def test_bundle_generation(
    evidence_resolution_runtime,
    evidence_resolution_plan,
    evidence_resolution_inputs,
):
    result = evidence_resolution_runtime.build_resolution_result(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
    )

    assert result.bundles
    assert all(bundle.bundle_id.startswith("evidence_bundle_") for bundle in result.bundles)
    assert all(bundle.evidence_ids and bundle.source_references for bundle in result.bundles)
