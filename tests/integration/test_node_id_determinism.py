def test_node_ids_are_deterministic(
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

    assert [node.node_id for node in first.graph.nodes] == [
        node.node_id for node in second.graph.nodes
    ]
