def test_graph_count_consistency(
    relationship_graph_runtime,
    relationship_graph_plan,
    relationship_graph_inputs,
):
    result = relationship_graph_runtime.execute_relationship_graph(
        relationship_graph_plan,
        *relationship_graph_inputs,
    )

    assert result.node_count == len(result.graph.nodes)
    assert result.edge_count == len(result.graph.edges)
    assert result.graph.node_count == result.node_count
    assert result.graph.edge_count == result.edge_count
