def test_evidence_collection(
    evidence_resolution_runtime,
    evidence_resolution_plan,
    evidence_resolution_inputs,
):
    collected = evidence_resolution_runtime.collect_evidence(
        evidence_resolution_plan,
        *evidence_resolution_inputs,
    )

    assert collected
    assert {item.source_type for item in collected} == {
        "CLAIM",
        "ENTITY",
        "EVENT",
        "GRAPH_EDGE",
        "TIMELINE_ENTRY",
    }
    assert all(item.evidence_id and item.evidence_text for item in collected)
