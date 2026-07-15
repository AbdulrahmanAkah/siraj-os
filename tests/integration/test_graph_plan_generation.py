def test_relationship_graph_plan_generation(
    relationship_graph_plan,
    event_claim_extraction_result,
    event_entity_extraction_result,
):
    assert relationship_graph_plan.graph_id.startswith("relationship_graph_")
    assert relationship_graph_plan.claim_extraction_result_id == (
        event_claim_extraction_result.result_id
    )
    assert relationship_graph_plan.entity_extraction_result_id == (
        event_entity_extraction_result.result_id
    )
    assert relationship_graph_plan.nodes == []
    assert relationship_graph_plan.edges == []
