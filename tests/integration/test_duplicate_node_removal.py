def test_duplicate_nodes_are_removed(
    relationship_graph_runtime,
    relationship_graph_inputs,
):
    claims, entities, events = relationship_graph_inputs
    nodes = relationship_graph_runtime.generate_nodes(claims, entities, events)
    node_ids = [node.node_id for node in nodes]

    assert len(node_ids) == len(set(node_ids))
