def test_edge_ids_are_deterministic(
    relationship_graph_runtime,
    relationship_graph_plan,
    relationship_graph_inputs,
):
    first = relationship_graph_runtime.execute_relationship_graph(
        relationship_graph_plan,
        *relationship_graph_inputs,
    )
    second = relationship_graph_runtime.execute_relationship_graph(
        relationship_graph_plan,
        *relationship_graph_inputs,
    )

    assert [edge.edge_id for edge in first.graph.edges] == [
        edge.edge_id for edge in second.graph.edges
    ]
