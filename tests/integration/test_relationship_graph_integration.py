def test_relationship_graph_integration(
    relationship_graph_runtime,
    relationship_graph_plan,
    relationship_graph_inputs,
):
    result = relationship_graph_runtime.execute_relationship_graph(
        relationship_graph_plan,
        *relationship_graph_inputs,
    )

    assert result.result_id.startswith("relationship_graph_result_")
    assert result.graph.nodes
    assert result.graph.edges
    assert all(
        edge.source_node_id in {node.node_id for node in result.graph.nodes}
        and edge.target_node_id in {node.node_id for node in result.graph.nodes}
        for edge in result.graph.edges
    )
